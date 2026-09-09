# -*- coding: utf-8 -*-
"""Bounded terrain creation routes for Revit 2026+ Toposolids."""
from pyrevit import routes, DB
from System.Collections.Generic import List
from utils import get_element_name, get_element_id_value, make_element_id, suppress_warnings
from terrain_validation import points_from_mm
from document_identity import require_expected_document
import json
import logging

logger = logging.getLogger(__name__)
def _exact_level(doc, data):
    if data.get('level_id') is not None and data.get('level_name') is not None:
        raise ValueError("pass either level_id or level_name, not both")
    levels = list(DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements())
    if data.get('level_id') is not None:
        level = doc.GetElement(make_element_id(data.get('level_id')))
        if not level or not isinstance(level, DB.Level):
            raise ValueError("level_id does not identify a Level")
        return level
    if data.get('level_name') is not None:
        matches = [level for level in levels if get_element_name(level) == data.get('level_name')]
        if len(matches) != 1:
            raise ValueError("level_name must match exactly one Level")
        return matches[0]
    if not levels:
        raise ValueError("the document has no Levels")
    return sorted(levels, key=lambda level: level.Elevation)[0]


def _exact_type(doc, data):
    if data.get('toposolid_type_id') is not None and data.get('toposolid_type_name') is not None:
        raise ValueError("pass either toposolid_type_id or toposolid_type_name, not both")
    types = list(DB.FilteredElementCollector(doc).OfClass(DB.ToposolidType).ToElements())
    if data.get('toposolid_type_id') is not None:
        topo_type = doc.GetElement(make_element_id(data.get('toposolid_type_id')))
        if not topo_type or not isinstance(topo_type, DB.ToposolidType):
            raise ValueError("toposolid_type_id does not identify a ToposolidType")
        return topo_type
    if data.get('toposolid_type_name') is not None:
        matches = [topo_type for topo_type in types if get_element_name(topo_type) == data.get('toposolid_type_name')]
        if len(matches) != 1:
            raise ValueError("toposolid_type_name must match exactly one ToposolidType")
        return matches[0]
    if not types:
        raise ValueError("the document has no Toposolid types")
    return types[0]


def register_terrain_routes(api):
    """Register the explicit-point Toposolid route. No code execution path."""
    @api.route('/create_toposolid/', methods=['POST'])
    def create_toposolid(doc, request):
        if not doc:
            return routes.make_response(data={'error': 'No active Revit document'}, status=503)
        try:
            data = json.loads(request.data) if isinstance(request.data, str) else (request.data or {})
            if not isinstance(data, dict):
                raise ValueError('request body must be a JSON object')
            raw_points, min_elevation_mm, max_elevation_mm = points_from_mm(data.get('points'))
            points = List[DB.XYZ]()
            for raw_point in raw_points:
                points.Add(DB.XYZ(raw_point[0], raw_point[1], raw_point[2]))
            level = _exact_level(doc, data)
            topo_type = _exact_type(doc, data)
            require_expected_document(doc, data)
        except Exception as error:
            return routes.make_response(data={'error': str(error)}, status=400)

        transaction = DB.Transaction(doc, 'Create Toposolid via MCP')
        try:
            transaction.Start()
            suppress_warnings(transaction)
            # Autodesk Revit 2026 API: Create(Document, IList<XYZ>, typeId, levelId).
            toposolid = DB.Toposolid.Create(doc, points, topo_type.Id, level.Id)
            if not toposolid:
                raise RuntimeError('Revit did not create a Toposolid')
            if transaction.Commit() != DB.TransactionStatus.Committed:
                raise RuntimeError('Toposolid transaction did not commit')
            return routes.make_response(data={
                'status': 'success',
                'document_title': doc.Title,
                'toposolid_id': get_element_id_value(toposolid),
                'toposolid_type_id': get_element_id_value(topo_type),
                'toposolid_type_name': get_element_name(topo_type),
                'level_id': get_element_id_value(level),
                'level_name': get_element_name(level),
                'point_count': points.Count,
                'min_elevation_mm': min_elevation_mm,
                'max_elevation_mm': max_elevation_mm,
            })
        except Exception as error:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
            logger.error('Failed to create Toposolid: %s', str(error))
            return routes.make_response(data={'error': str(error)}, status=500)

    logger.info('Terrain routes registered successfully')
