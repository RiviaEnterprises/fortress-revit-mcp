# -*- coding: utf-8 -*-
"""Pure validation for the Toposolid HTTP contract, runnable without Revit."""

MM_TO_FEET = 1.0 / 304.8
MAX_POINTS = 10000
MAX_ABS_MM = 10000000.0


def _finite_mm(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number == float('inf') or number == float('-inf'):
        return None
    return number if abs(number) <= MAX_ABS_MM else None


def points_from_mm(raw):
    if not isinstance(raw, list) or len(raw) < 3 or len(raw) > MAX_POINTS:
        raise ValueError('points must contain 3 to {} XYZ points'.format(MAX_POINTS))
    points = []
    elevations = []
    for index, point in enumerate(raw):
        if not isinstance(point, dict) or set(point.keys()) - set(['x', 'y', 'z']):
            raise ValueError('point {} must be an XYZ object'.format(index))
        x, y, z = (_finite_mm(point.get(axis)) for axis in ('x', 'y', 'z'))
        if x is None or y is None or z is None:
            raise ValueError('point {} has non-finite or out-of-bounds millimetres'.format(index))
        points.append((x * MM_TO_FEET, y * MM_TO_FEET, z * MM_TO_FEET))
        elevations.append(z)
    return points, min(elevations), max(elevations)
