"""
ryu_app.py — Ryu SDN controller for the Emergency Notification Network.

Features (D1):
  - OpenFlow 1.3 switch handshake
  - L2 learning-switch forwarding
  - Emergency traffic classification (UDP dst port 9999 -> high-priority queue)
  - Port-statistics monitoring thread
  - REST API endpoint for application events

Run with:
    python controller/run_ryu.py controller/ryu_app.py --observe-links
"""

import json
import os
import time
import threading
from collections import defaultdict

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (
    CONFIG_DISPATCHER,
    DEAD_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls,
)
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, udp, arp
from ryu.lib import hub
from ryu.app.wsgi import ControllerBase, WSGIApplication, route

import logging

LOG = logging.getLogger("EmergencySDN")

EMERGENCY_INSTANCE = "emergency_controller"


def _load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "config.json")
    try:
        with open(config_path) as f:
            return json.load(f)
    except FileNotFoundError:
        LOG.warning("config.json not found, using defaults")
        return {}


class EmergencyController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {"wsgi": WSGIApplication}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cfg = _load_config()

        ctrl = self.cfg.get("controller", {})
        proto = self.cfg.get("protocol", {})

        self.emergency_port = proto.get("emergency_port", 9999)
        self.stats_interval = ctrl.get("stats_poll_interval_s", 2)
        self.congestion_thresh = ctrl.get("congestion_threshold_percent", 70)
        self.em_queue = ctrl.get("emergency_queue_id", 1)
        self.default_queue = ctrl.get("default_queue_id", 0)

        # per-switch MAC table:  {dpid: {mac: port}}
        self.mac_to_port = defaultdict(dict)

        # port stats history: {dpid: {port_no: (prev_ts, prev_tx, prev_rx)}}
        self.port_stats = defaultdict(dict)

        # track congested ports
        self.congested = defaultdict(set)

        # REST API
        wsgi = kwargs["wsgi"]
        wsgi.register(EmergencyRestApi, {EMERGENCY_INSTANCE: self})

        # stats polling greenlet
        self.monitor_thread = hub.spawn(self._stats_poller)

    # ──────────────────────────────────────────────────────────────────────
    # Switch connection
    # ──────────────────────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        LOG.info("[SDN] Switch s%s connected (dpid=%s)", dp.id, dp.id)

        # Default table-miss: send to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self._add_flow(dp, 0, match, actions, table_id=0)

        # Emergency UDP flow — high priority
        match_em = parser.OFPMatch(
            eth_type=0x0800,       # IPv4
            ip_proto=17,           # UDP
            udp_dst=self.emergency_port,
        )
        # Action: set queue + send to controller (controller will output to correct port)
        actions_em = [
            parser.OFPActionSetQueue(self.em_queue),
            parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER),
        ]
        self._add_flow(dp, 100, match_em, actions_em, table_id=0)

        LOG.info("[SDN] Emergency flow installed on s%s (udp_dst=%d, queue=%d)",
                 dp.id, self.emergency_port, self.em_queue)

    # ──────────────────────────────────────────────────────────────────────
    # Packet-In — L2 learning switch
    # ──────────────────────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return

        dst = eth.dst
        src = eth.src
        dpid = dp.id

        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofp.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Only install a flow for unicast (known dst) to avoid flooding rules
        if out_port != ofp.OFPP_FLOOD:
            # Check if this is emergency traffic
            ipv4_pkt = pkt.get_protocol(ipv4.ipv4)
            udp_pkt = pkt.get_protocol(udp.udp)
            is_emergency = (ipv4_pkt and udp_pkt and udp_pkt.dst_port == self.emergency_port)

            if is_emergency:
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_dst=dst,
                    eth_src=src,
                    eth_type=0x0800,
                    ip_proto=17,
                    udp_dst=self.emergency_port,
                )
                actions = [
                    parser.OFPActionSetQueue(self.em_queue),
                    parser.OFPActionOutput(out_port),
                ]
                self._add_flow(dp, 200, match, actions, idle_timeout=30)
                LOG.info("[SDN] Emergency data-path flow installed on s%s: port %s -> port %s",
                         dpid, in_port, out_port)
            else:
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
                self._add_flow(dp, 1, match, actions, idle_timeout=60)

        data = None
        if msg.buffer_id == ofp.OFP_NO_BUFFER:
            data = msg.data

        out_msg = parser.OFPPacketOut(
            datapath=dp, buffer_id=msg.buffer_id,
            in_port=in_port, actions=actions, data=data,
        )
        dp.send_msg(out_msg)

    # ──────────────────────────────────────────────────────────────────────
    # Port statistics
    # ──────────────────────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        now = time.time()

        for stat in ev.msg.body:
            port_no = stat.port_no
            if port_no >= 0xFFFFFF00:
                continue  # skip LOCAL/special ports

            tx_bytes = stat.tx_bytes
            rx_bytes = stat.rx_bytes

            prev = self.port_stats[dpid].get(port_no)
            if prev:
                prev_ts, prev_tx, prev_rx = prev
                dt = now - prev_ts
                if dt > 0:
                    # bits per second
                    tx_bps = (tx_bytes - prev_tx) * 8 / dt
                    rx_bps = (rx_bytes - prev_rx) * 8 / dt
                    # assume 10 Mbps links for utilization
                    link_bps = 10_000_000
                    util = max(tx_bps, rx_bps) / link_bps * 100
                    if util >= self.congestion_thresh:
                        if port_no not in self.congested[dpid]:
                            self.congested[dpid].add(port_no)
                            LOG.warning("[SDN] s%s port=%d utilization=%.1f%% — CONGESTION",
                                        dpid, port_no, util)
                    else:
                        self.congested[dpid].discard(port_no)

            self.port_stats[dpid][port_no] = (now, tx_bytes, rx_bytes)

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _add_flow(dp, priority, match, actions, table_id=0,
                  idle_timeout=0, hard_timeout=0):
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=dp, priority=priority, match=match,
            instructions=inst, table_id=table_id,
            idle_timeout=idle_timeout, hard_timeout=hard_timeout,
        )
        dp.send_msg(mod)

    # ──────────────────────────────────────────────────────────────────────
    # Stats request helpers (called from poller)
    # We store datapaths so the poller can send stats requests
    # ──────────────────────────────────────────────────────────────────────

    _datapaths = {}

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self._datapaths[dp.id] = dp
        elif ev.state == DEAD_DISPATCHER:
            self._datapaths.pop(dp.id, None)

    def _stats_poller(self):
        while True:
            for dpid, dp in list(self._datapaths.items()):
                parser = dp.ofproto_parser
                req = parser.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY)
                dp.send_msg(req)
            hub.sleep(self.stats_interval)


# ──────────────────────────────────────────────────────────────────────────
# REST API — receives events from the notification server
# ──────────────────────────────────────────────────────────────────────────

class EmergencyRestApi(ControllerBase):
    def __init__(self, req, link, data, **config):
        super().__init__(req, link, data, **config)
        self.ctrl = data[EMERGENCY_INSTANCE]

    @route("event", "/api/event", methods=["POST"])
    def handle_event(self, req, **kwargs):
        try:
            body = json.loads(req.body)
            event = body.get("event", "unknown")
            LOG.info("[SDN:API] Application event received: %s  data=%s", event, body)
        except Exception as e:
            LOG.error("[SDN:API] Bad request: %s", e)
        return json.dumps({"status": "ok"}).encode("utf-8")
