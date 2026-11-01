import copy
import datetime as dt
import json
import tempfile
import unittest
from unittest.mock import patch

from aplicacion_terral import demo
from aplicacion_terral.comun import HORIZONTES
from aplicacion_terral.g2 import almacen as a
from aplicacion_terral.ha3 import operacion as ha3
from aplicacion_terral.inferencia import EntradaInvalida, cargar_modelo, predictores, probabilidades, ventana


class DemoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # El flujo público debe funcionar aun cuando la red esté prohibida.
        self.network = patch('socket.socket', side_effect=AssertionError('La demo no usa red'))
        self.network.start()
        self.addCleanup(self.network.stop)
        demo.preparar(self.temp.name)
        self.app = demo.crear_aplicacion(self.temp.name)

    def get(self, path, query='', method='GET'):
        response = {}
        body = b''.join(self.app(dict(PATH_INFO=path, QUERY_STRING=query,
                                     REQUEST_METHOD=method),
                                lambda status, headers: response.update(status=status, headers=dict(headers))))
        return response, body

    def test_seis_modelos_y_trazabilidad(self):
        response, raw = self.get('/api/actual')
        result = json.loads(raw)
        self.assertEqual(response['status'], '200 OK')
        self.assertTrue(result['datos_sinteticos'])
        self.assertEqual(len(result['series']), 70)
        self.assertEqual(set(result['estimacion']), {str(h) for h in HORIZONTES})
        t, rows = ventana(demo.registros_sinteticos(), '2023-06-15 16:00:00')
        expected = probabilidades(predictores(t, rows), cargar_modelo())
        for h, value in result['estimacion'].items():
            self.assertEqual(value['probabilidad'], expected[h])

    def test_conserva_publicacion_durante_ciclo_interrumpido(self):
        before = self.get('/api/actual')[1]
        with a.conexion(self.temp.name) as db:
            db.execute('INSERT INTO ciclos VALUES(?,?)', ('interrumpido', demo.CORTE))
        after = json.loads(self.get('/api/actual')[1])
        self.assertEqual(json.loads(before)['estimacion'], after['estimacion'])
        self.assertEqual(after['operacion']['estado_escritor'], 'sin_cierre')

    def test_caducidad_no_rejuvenece_entradas(self):
        with a.conexion(self.temp.name, lectura=True) as db:
            future = (dt.datetime.fromisoformat(demo.CORTE)+dt.timedelta(hours=3)).isoformat()
            result = ha3.panel(db, future)
        self.assertIsNone(result['estimacion'])
        self.assertTrue(result['ultimo_resultado_registrado'])

    def test_huecos_y_duplicados_rechazados(self):
        rows = demo.registros_sinteticos()
        for invalid in (rows[:-1], rows+[copy.deepcopy(rows[-1])]):
            with self.assertRaises(EntradaInvalida):
                ventana(invalid, '2023-06-15 16:00:00')

    def test_recursos_y_limites(self):
        for path in ('/', '/metodologia'):
            response, body = self.get(path)
            self.assertEqual(response['status'], '200 OK')
            self.assertIn('Datos sintéticos'.encode(), body)
        for path in ('/app.js', '/style.css', '/api/emisiones'):
            self.assertEqual(self.get(path)[0]['status'], '200 OK')
        self.assertTrue(self.get('/../../etc/passwd')[0]['status'].startswith('404'))
        self.assertTrue(self.get('/api/historico')[0]['status'].startswith('404'))
        self.assertTrue(self.get('/', 'a=1')[0]['status'].startswith('400'))
        self.assertTrue(self.get('/', method='POST')[0]['status'].startswith('405'))


if __name__ == '__main__':
    unittest.main()
