import os
import importlib.util
import sys
import types
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location('terrain_validation', os.path.join(ROOT, 'revit_mcp', 'terrain_validation.py'))
TERRAIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TERRAIN)


def load_documentation_with_fake_revit():
    """Load the real route module against a minimal executable Revit façade."""
    handlers = {}

    class FakeTransaction(object):
        instances = []

        def __init__(self, doc, name):
            self.started = False
            self.ended = False
            self.rolled_back = False
            FakeTransaction.instances.append(self)

        def Start(self):
            self.started = True

        def Commit(self):
            self.ended = True

        def RollBack(self):
            self.rolled_back = True
            self.ended = True

        def HasStarted(self):
            return self.started

        def HasEnded(self):
            return self.ended

    class FakeImageOptions(object):
        def SetViewsAndSheets(self, view_ids):
            pass

    class FakeList(list):
        @classmethod
        def __class_getitem__(cls, item):
            return cls

        def Add(self, value):
            self.append(value)

    class FakeViewSet(object):
        def Insert(self, value):
            pass

    class FakeImageFileType(object):
        PNG = object()
        JPGMedium = object()

    fake_db = types.SimpleNamespace(
        Transaction=FakeTransaction,
        ImageExportOptions=FakeImageOptions,
        ZoomFitType=types.SimpleNamespace(FitToPage=object()),
        ImageResolution=types.SimpleNamespace(DPI_150=object()),
        ExportRange=types.SimpleNamespace(SetOfViews=object()),
        ImageFileType=FakeImageFileType,
        ViewSet=FakeViewSet,
        ElementId=object,
    )
    fake_routes = types.SimpleNamespace(make_response=lambda data, status=200: {'data': data, 'status': status})
    fake_pyrevit = types.ModuleType('pyrevit')
    fake_pyrevit.routes = fake_routes
    fake_pyrevit.revit = object()
    fake_pyrevit.DB = fake_db
    fake_utils = types.ModuleType('utils')
    fake_utils.get_element_name = lambda view: getattr(view, 'Name', 'Fake View')
    fake_utils.get_element_id_value = lambda element: 1
    fake_utils.suppress_warnings = lambda transaction: None
    fake_identity = types.ModuleType('document_identity')
    fake_identity.require_expected_document = lambda doc, data: None
    fake_system = types.ModuleType('System')
    fake_collections = types.ModuleType('System.Collections')
    fake_generic = types.ModuleType('System.Collections.Generic')
    fake_generic.List = FakeList
    sys.modules['pyrevit'] = fake_pyrevit
    sys.modules['utils'] = fake_utils
    sys.modules['document_identity'] = fake_identity
    sys.modules['System'] = fake_system
    sys.modules['System.Collections'] = fake_collections
    sys.modules['System.Collections.Generic'] = fake_generic

    module_spec = importlib.util.spec_from_file_location(
        'documentation_fake_revit', os.path.join(ROOT, 'revit_mcp', 'documentation.py')
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    module.basestring = str

    class FakeApi(object):
        def route(self, route_path, methods):
            def register(handler):
                handlers[route_path] = handler
                return handler
            return register

    module.register_documentation_routes(FakeApi())

    class FakeOutputPath(object):
        def __getattr__(self, name):
            return getattr(os.path, name)

        def isabs(self, value):
            return True

        def isdir(self, value):
            return True

        def exists(self, value):
            return False

        def isfile(self, value):
            return False

    class FakeOutputOs(object):
        path = FakeOutputPath()

        def listdir(self, value):
            return []

    fake_output_os = FakeOutputOs()
    module.os = fake_output_os
    return module, handlers['/export_document/'], FakeTransaction, fake_output_os


class FakeExportDocument(object):
    Title = 'Fake Model'
    ActiveView = types.SimpleNamespace(Name='Fake View', Id=object())

    def ExportImage(self, options):
        # Deliberately produces no output for the rollback contract test.
        pass


class TerrainRouteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documentation_module, cls.export_document_handler, cls.fake_transactions, cls.fake_output_os = load_documentation_with_fake_revit()

    def setUp(self):
        with open(os.path.join(ROOT, 'revit_mcp', 'terrain.py'), 'r') as source:
            self.source = source.read()
        with open(os.path.join(ROOT, 'startup.py'), 'r') as source:
            self.startup = source.read()
        with open(os.path.join(ROOT, 'revit_mcp', 'status.py'), 'r') as source:
            self.status = source.read()
        with open(os.path.join(ROOT, 'revit_mcp', 'building.py'), 'r') as source:
            self.building = source.read()
        with open(os.path.join(ROOT, 'revit_mcp', 'documentation.py'), 'r') as source:
            self.documentation = source.read()
        with open(os.path.join(ROOT, 'revit_mcp', 'interop.py'), 'r') as source:
            self.interop = source.read()

    def test_route_is_registered_with_bounded_explicit_xyz_contract(self):
        self.assertIn("@api.route('/create_toposolid/', methods=['POST'])", self.source)
        self.assertIn('points_from_mm(data.get(\'points\'))', self.source)
        self.assertIn('register_terrain_routes(api)', self.startup)
        self.assertIn('"document_fingerprint": document_fingerprint(doc)', self.status)
        self.assertIn('require_expected_document(doc, data)', self.source)
        self.assertIn('DB.TransactionStatus.Committed', self.source)

    def test_acceptance_mutations_guard_fingerprint_immediately_before_write(self):
        for source in (self.building, self.documentation, self.interop):
            self.assertIn('require_expected_document(doc, data)', source)
        self.assertLess(self.building.index('require_expected_document(doc, data)'), self.building.index('DB.Transaction(doc, "Create Levels")'))
        self.assertLess(self.documentation.index('require_expected_document(doc, data)'), self.documentation.index('DB.Transaction(doc, "Export Document via MCP")'))
        self.assertLess(self.interop.index('require_expected_document(doc, data)'), self.interop.index('DB.Transaction(doc, "Export IFC via MCP")'))

    def test_exports_require_current_call_outputs_without_shared_newest_file_scans(self):
        self.assertIn("output_dir must be empty for this export call", self.documentation)
        self.assertIn("Image export did not produce exactly one new requested-format file", self.documentation)
        self.assertIn("success = doc.Export(export_dir, os.path.splitext(output_filename)[0], view_ids, dwg_options)", self.documentation)
        self.assertIn("DWG export API returned failure", self.documentation)
        self.assertIn("file_size_bytes = os.path.getsize(file_path)", self.documentation)
        self.assertNotIn('getmtime', self.documentation)
        self.assertNotIn('candidates = []', self.documentation)
        self.assertIn('success = doc.Export(output_dir or ".", file_name, ifc_options)', self.interop)
        self.assertIn('IFC export API returned failure', self.interop)
        self.assertIn('file_size_bytes = os.path.getsize(file_path)', self.interop)
        self.assertIn('IFC export produced no requested nonempty file', self.interop)
        self.assertNotIn('getmtime', self.interop)

    def test_image_zero_outputs_rolls_back_the_started_transaction(self):
        self.fake_transactions.instances[:] = []
        response = type(self).export_document_handler(
            FakeExportDocument(),
            types.SimpleNamespace(data={
                'format': 'png',
                'output_dir': 'C:\\pc-agent\\empty-job',
                'output_filename': 'export.png',
            }),
        )
        self.assertEqual(response['status'], 500)
        self.assertIn('exactly one new requested-format file', response['data']['error'])
        self.assertEqual(len(self.fake_transactions.instances), 1)
        transaction = self.fake_transactions.instances[0]
        self.assertTrue(transaction.rolled_back)
        self.assertTrue(transaction.ended)

    def test_missing_jpg_encoder_fails_before_transaction_without_png_fallback(self):
        self.fake_transactions.instances[:] = []
        image_types = self.documentation_module.DB.ImageFileType
        original = image_types.JPGMedium
        delattr(image_types, 'JPGMedium')
        try:
            response = type(self).export_document_handler(
                FakeExportDocument(),
                types.SimpleNamespace(data={
                    'format': 'jpg',
                    'output_dir': 'C:\\pc-agent\\empty-job',
                    'output_filename': 'export.jpg',
                }),
            )
            self.assertEqual(self.fake_output_os.listdir('C:\\pc-agent\\empty-job'), [])
        finally:
            image_types.JPGMedium = original
        self.assertEqual(response['status'], 500)
        self.assertIn('JPG export is unavailable', response['data']['error'])
        self.assertEqual(self.fake_transactions.instances, [])

    def test_transaction_uses_official_toposolid_create_signature_and_rolls_back(self):
        self.assertIn('DB.Toposolid.Create(doc, points, topo_type.Id, level.Id)', self.source)
        self.assertIn("DB.Transaction(doc, 'Create Toposolid via MCP')", self.source)
        self.assertIn('transaction.RollBack()', self.source)
        self.assertIn("'toposolid_id'", self.source)
        self.assertIn("'min_elevation_mm'", self.source)

    def test_bounded_xyz_validation_rejects_empty_nonfinite_and_oversized_inputs(self):
        with self.assertRaises(ValueError):
            TERRAIN.points_from_mm([])
        with self.assertRaises(ValueError):
            TERRAIN.points_from_mm([{'x': 0, 'y': 0, 'z': 0}] * 10001)
        with self.assertRaises(ValueError):
            TERRAIN.points_from_mm([{'x': 0, 'y': 0, 'z': 0}, {'x': 1, 'y': 0, 'z': 0}, {'x': float('inf'), 'y': 1, 'z': 0}])
        points, low, high = TERRAIN.points_from_mm([{'x': 0, 'y': 0, 'z': -10}, {'x': 304.8, 'y': 0, 'z': 0}, {'x': 0, 'y': 304.8, 'z': 20}])
        self.assertEqual(len(points), 3)
        self.assertEqual(points[1][0], 1.0)
        self.assertEqual((low, high), (-10.0, 20.0))


if __name__ == '__main__':
    unittest.main()
