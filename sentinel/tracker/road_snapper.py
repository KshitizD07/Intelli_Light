"""
sentinel/tracker/road_snapper.py
=================================
Maps sequences of junction IDs to actual street network geometries.

Instead of drawing straight 'dot-to-dot' lines on the map, this module
uses sumolib's road network topology to reconstruct the physical
street polylines between consecutive camera sightings.

Outputs GeoJSON LineString coordinates [[lng, lat], ...] suitable
for Leaflet / Mapbox rendering.
"""

import os
import math
import logging
from typing import List, Tuple, Dict, Optional, Any

import sumolib
from sentinel.config import SUMO_NET_FILE

logger = logging.getLogger(__name__)

_SHARED_NET_CACHE: Dict[str, Any] = {}

def get_shared_sumo_net(net_file: str = SUMO_NET_FILE):
    """Returns a cached sumolib net instance, parsing the XML only once per process."""
    global _SHARED_NET_CACHE
    if net_file in _SHARED_NET_CACHE:
        return _SHARED_NET_CACHE[net_file]

    if not os.path.isfile(net_file):
        logger.warning(f"[SUMONetCache] Network file not found: {net_file}")
        return None
    try:
        net = sumolib.net.readNet(net_file, withInternal=False)
        _SHARED_NET_CACHE[net_file] = net
        logger.info(f"[SUMONetCache] Loaded {net_file} into memory cache")
        return net
    except Exception as e:
        logger.error(f"[SUMONetCache] Failed to load {net_file}: {e}")
        return None


class RoadSnapper:
    """
    Reconstructs continuous road geometry between junction checkpoints.
    """

    def __init__(self, net_file: str = SUMO_NET_FILE):
        self.net_file = net_file
        self._net = get_shared_sumo_net(net_file)
        self._cache: Dict[Tuple[str, str], List[Tuple[float, float]]] = {}

    def get_route_geometry(self, junction_sequence: List[str]) -> List[Tuple[float, float]]:
        """
        Given a sequence of junction IDs (e.g. ['J1', 'J2', 'J3']), returns
        an ordered list of geographic coordinates [(lng, lat), ...] following
        the physical road edges.
        """
        if not junction_sequence:
            return []
        if len(junction_sequence) == 1:
            coord = self.get_junction_coord(junction_sequence[0])
            return [coord] if coord else []

        full_coords: List[Tuple[float, float]] = []

        for i in range(len(junction_sequence) - 1):
            src = junction_sequence[i]
            dst = junction_sequence[i + 1]
            pair_coords = self._get_edge_geometry(src, dst)
            if not pair_coords:
                # Fallback to straight line between the two junction points
                c1 = self.get_junction_coord(src)
                c2 = self.get_junction_coord(dst)
                if c1 and c2:
                    pair_coords = [c1, c2]

            if pair_coords:
                if full_coords and full_coords[-1] == pair_coords[0]:
                    full_coords.extend(pair_coords[1:])
                else:
                    full_coords.extend(pair_coords)

        return full_coords

    def _get_edge_geometry(self, from_jid: str, to_jid: str) -> List[Tuple[float, float]]:
        cache_key = (from_jid, to_jid)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self._net is None:
            return []

        try:
            from_node = self._net.getNode(from_jid)
            to_node = self._net.getNode(to_jid)
            if not from_node or not to_node:
                return []

            # Find connecting edge directly
            connecting_edge = None
            for edge in from_node.getOutgoing():
                if edge.getToNode().getID() == to_jid:
                    connecting_edge = edge
                    break

            coords = []
            if connecting_edge:
                # Convert shape 2D (x, y) to (lng, lat)
                shape = connecting_edge.getShape()
                for x, y in shape:
                    try:
                        lng, lat = self._net.convertXY2LonLat(x, y)
                        coords.append((round(lng, 6), round(lat, 6)))
                    except Exception:
                        pass
            else:
                # Fallback: node to node
                x1, y1 = from_node.getCoord()
                x2, y2 = to_node.getCoord()
                lng1, lat1 = self._net.convertXY2LonLat(x1, y1)
                lng2, lat2 = self._net.convertXY2LonLat(x2, y2)
                coords = [(round(lng1, 6), round(lat1, 6)), (round(lng2, 6), round(lat2, 6))]

            self._cache[cache_key] = coords
            return coords
        except Exception:
            return []

    def get_junction_coord(self, jid: str) -> Optional[Tuple[float, float]]:
        if self._net is None:
            return None
        try:
            node = self._net.getNode(jid)
            if node:
                x, y = node.getCoord()
                lng, lat = self._net.convertXY2LonLat(x, y)
                return (round(lng, 6), round(lat, 6))
        except Exception:
            pass
        return None
