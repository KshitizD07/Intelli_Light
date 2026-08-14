"""
Intelli-Light NTCIP 1202 Hardware Controller
=============================================

Implements the NTCIP 1202-2005 standard for communicating with
physical Traffic Signal Controllers (TLCs) via SNMP.

This bridge allows the RL model to control real-world cabinets
from Siemens, Yunex, Econolite, etc., without custom hardware.
"""

import time
import logging
from typing import Dict, List, Optional
from pysnmp.hlapi import *

logger = logging.getLogger(__name__)

# Standard NTCIP 1202 OIDs (Object Identifiers)
# Format: iso.org.dod.internet.private.enterprises.nema.ntcip.devices.asc.ascPhase...
NTCIP_PREFIX = "1.3.6.1.4.1.1206.4.2.1.1"

OIDS = {
    "phaseControlGroupHold":   f"{NTCIP_PREFIX}.5.1.2.1", # Phase Hold (Force phase to stay)
    "phaseControlGroupForceOff": f"{NTCIP_PREFIX}.5.1.3.1", # Phase Force-Off (End phase)
    "phaseControlGroupOmit":     f"{NTCIP_PREFIX}.5.1.1.1", # Phase Omit (Skip phase)
    "phaseStatusGroupGreen":     f"{NTCIP_PREFIX}.4.1.2.1", # Current Green Status
}

class NTCIPController:
    """
    Bridge between Intelli-Light RL decisions and NTCIP-compatible hardware.
    """
    
    def __init__(
        self, 
        ip_address: str, 
        port: int = 161, 
        community: str = "public",
        timeout: int = 1
    ):
        self.ip_address = ip_address
        self.port = port
        self.community = community
        self.timeout = timeout
        
        self.target = UdpTransportTarget((ip_address, port), timeout=timeout)
        self.auth_data = CommunityData(community)
        
        logger.info(f"NTCIP Controller initialized for {ip_address}:{port}")

    def get_current_greens(self) -> int:
        """
        Query the TLC for currently active green phases.
        Returns a bitmask where Bit 0 = Phase 1, Bit 1 = Phase 2, etc.
        """
        iterator = getCmd(
            SnmpEngine(),
            self.auth_data,
            self.target,
            ContextData(),
            ObjectType(ObjectIdentity(OIDS["phaseStatusGroupGreen"]))
        )

        errorIndication, errorStatus, errorIndex, varBinds = next(iterator)

        if errorIndication:
            logger.error(f"SNMP GET Error: {errorIndication}")
            return 0
        elif errorStatus:
            logger.error(f"SNMP Status Error: {errorStatus.prettyPrint()}")
            return 0
        else:
            return int(varBinds[0][1])

    def set_phase_hold(self, phase_mask: int):
        """
        Force the TLC to HOLD specific phases.
        
        Args:
            phase_mask: Bitmask of phases to hold (e.g., 0b00001100 for phases 3 and 4).
        """
        iterator = setCmd(
            SnmpEngine(),
            self.auth_data,
            self.target,
            ContextData(),
            ObjectType(ObjectIdentity(OIDS["phaseControlGroupHold"]), Integer(phase_mask))
        )
        
        errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
        
        if errorIndication:
            logger.error(f"SNMP SET (Hold) Error: {errorIndication}")
        elif errorStatus:
            logger.error(f"SNMP Status Error: {errorStatus.prettyPrint()}")
        else:
            logger.debug(f"Applied Phase Hold: {bin(phase_mask)}")

    def set_phase_force_off(self, phase_mask: int):
        """
        Force the TLC to terminate specific phases (Force-Off).
        """
        iterator = setCmd(
            SnmpEngine(),
            self.auth_data,
            self.target,
            ContextData(),
            ObjectType(ObjectIdentity(OIDS["phaseControlGroupForceOff"]), Integer(phase_mask))
        )
        next(iterator)

    def apply_rl_decision(self, phase_idx: int, duration: int):
        """
        Translate an RL decision (Phase X for Y seconds) into NTCIP commands.
        
        Logic:
        1. Set 'Hold' for the requested phase.
        2. Wait for 'duration' seconds.
        3. Clear 'Hold' and trigger 'Force-Off'.
        """
        # NTCIP phases are usually 1-indexed. RL is 0-indexed.
        # Mapping RL Phase 0..3 to NTCIP bitmask.
        # Phase 0 -> Bit 0 (1), Phase 1 -> Bit 1 (2), etc.
        phase_mask = 1 << phase_idx
        
        logger.info(f"Applying RL Decision: Phase {phase_idx+1} for {duration}s")
        
        # 1. Hold the phase
        self.set_phase_hold(phase_mask)
        
        # 2. Monitor and wait (in real deployment, this would be non-blocking)
        time.sleep(duration)
        
        # 3. Release and Force-Off to move to next phase
        self.set_phase_hold(0)
        self.set_phase_force_off(phase_mask)

class ShadowController(NTCIPController):
    """
    "Shadow Mode" controller that logs commands but does NOT send them to hardware.
    Used for the first 14 days of a pilot to build trust.
    """
    def set_phase_hold(self, phase_mask: int):
        logger.info(f"[SHADOW MODE] Would Hold: {bin(phase_mask)}")

    def set_phase_force_off(self, phase_mask: int):
        logger.info(f"[SHADOW MODE] Would Force-Off: {bin(phase_mask)}")

if __name__ == "__main__":
    # Test with a mock/real IP
    logging.basicConfig(level=logging.INFO)
    ctrl = ShadowController("192.168.1.100")
    ctrl.apply_rl_decision(0, 15) # Phase 1 for 15s
