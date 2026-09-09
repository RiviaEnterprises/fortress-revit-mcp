# -*- coding: utf-8 -*-
"""Opaque active-document identity for guarded HTTP mutations."""
import hashlib


def document_fingerprint(doc):
    try:
        project_id = str(doc.ProjectInformation.UniqueId or '')
    except Exception:
        project_id = ''
    try:
        path = str(doc.PathName or '').replace('\\', '/').lower()
    except Exception:
        path = ''
    # Path participates in identity but is never returned to callers.
    return hashlib.sha256((project_id + '\0' + path).encode('utf-8')).hexdigest()


def require_expected_document(doc, data):
    expected_title = data.get('expected_document')
    expected_fingerprint = data.get('expected_document_fingerprint')
    if not isinstance(expected_title, basestring) or expected_title != doc.Title:
        raise ValueError('active document title does not match the confirmed document')
    if not isinstance(expected_fingerprint, basestring) or expected_fingerprint != document_fingerprint(doc):
        raise ValueError('active document fingerprint does not match the confirmed document')
