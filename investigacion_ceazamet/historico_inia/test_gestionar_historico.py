"""Pruebas locales de conservación, datos vacíos, sensores opcionales y parada."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "piloto_2025_07/vicuna_2025-07-01_2025-07-07_original.xls"
MODULE = Path(__file__).with_name("gestionar_historico.py")


class HistoricalTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("history", MODULE)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.temp = tempfile.TemporaryDirectory()
        self.m.ROOT = Path(self.temp.name)
        self.db = self.m.connect()
        self.config = {"start": "2025-07-01", "end": "2025-07-07", "pause_blocks_seconds": 15, "pause_post_get_seconds": 10}
        self.job = {"id": "fixture", "start": "2025-07-01", "end": "2025-07-07", "sensors": self.m.ALL, "role": "completo"}
        self.db.execute("INSERT INTO jobs(id,spec) VALUES(?,?)", ("fixture", json.dumps(self.job)))
        self.db.commit()
        self.directory = self.m.ROOT / "originales/fixture"
        self.directory.mkdir(parents=True)
        shutil.copyfile(SOURCE, self.directory / "original.xls")
        manifest = json.loads(SOURCE.with_suffix(".manifest.json").read_text())
        # Simula una solicitud de 7 sensores cuyo XLS válido omite los opcionales
        # a 5 m. El archivo meteorológico de prueba permanece intacto.
        manifest["fields"] = [(k,v) for k,v in manifest["fields"] if k != "s_cod[]"] + [("s_cod[]",s) for s in self.m.ALL]
        self.m.atomic_json(self.directory / "manifest.json", manifest)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_missing_optional_headers_dont_reject_primary(self):
        info = self.m.verify_file(self.db,self.job,self.directory,self.config)
        self.assertEqual(info["sensors_absent"],["VCNVV5","VCNDV5"])
        self.assertEqual(info["status"],"verificado_con_datos")
        result = self.m.rebuild_reports(self.db,self.config,export=True)
        self.assertEqual(result["main_usable_unique_hours"],168)
        self.assertEqual(self.m.sha(SOURCE),self.m.sha(self.directory/"original.xls"))

    def test_all_missing_is_valid_no_data_not_download_error(self):
        book = self.m.xlrd.open_workbook(SOURCE)
        real = book.sheet_by_index(0)
        class EmptySheet:
            ncols,nrows,name=real.ncols,real.nrows,real.name
            def cell_value(self,*args):
                return real.cell_value(*args)
            def cell_type(self,*args):
                return real.cell_type(*args)
            def row_values(self,i):
                row=real.row_values(i)
                if i>=4 and self_m.re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",str(row[0])):
                    row[1:]=["","","",0.0]*5
                return row
        self_m=self.m
        class EmptyBook:
            biff_version=book.biff_version
            def sheet_by_index(self,i):
                return EmptySheet()
        with patch.object(self.m.xlrd,"open_workbook",return_value=EmptyBook()):
            info=self.m.verify_file(self.db,self.job,self.directory,self.config)
        self.assertEqual(info["status"],"verificado_sin_datos")
        self.assertEqual(self.db.execute("SELECT sum(usable) FROM observations").fetchone()[0],0)

    def test_hash_changes_are_rejected(self):
        with (self.directory/"original.xls").open("ab") as f:
            f.write(b"modified")
        with self.assertRaisesRegex(ValueError,"hash"):
            self.m.verify_file(self.db,self.job,self.directory,self.config)

    def test_successful_get_after_local_interruption_needs_no_http(self):
        manifest=json.loads((self.directory/"manifest.json").read_text())
        (self.directory/"manifest.json").unlink()
        self.m.atomic_json(self.directory/"adquisicion.json",manifest)
        shutil.copyfile(self.directory/"original.xls",self.directory/"get.body")
        (self.directory/"original.xls").unlink()
        self.m.atomic_json(self.directory/"get.http.json",{"curl_exit":0,"http_status":"200","url":"https://www.ceazamet.cl/temp/test.xls","finished_utc":self.m.now(),"body_sha256":self.m.sha(self.directory/"get.body")})
        with patch.object(self.m,"request") as request:
            info=self.m.download_one(self.db,self.job,self.config)
        request.assert_not_called()
        self.assertEqual(info["status"],"verificado_con_datos")

    def test_duplicate_sensor_hour_is_preserved_and_not_jointly_usable(self):
        self.m.verify_file(self.db,self.job,self.directory,self.config)
        row=list(self.db.execute("SELECT * FROM observations WHERE sensor='39' LIMIT 1").fetchone())
        row[14]=9999
        self.db.execute("INSERT INTO observations VALUES("+",".join("?"*18)+")",row)
        self.db.commit()
        result=self.m.rebuild_reports(self.db,self.config,export=True)
        self.assertEqual(result["duplicates_sensor_hours"],1)
        self.assertEqual(result["main_usable_unique_hours"],167)
        self.assertEqual(self.db.execute("SELECT count(*) FROM observations").fetchone()[0],841)

    def test_block_stops_future_network_requests(self):
        self.m.verify_file(self.db,self.job,self.directory,self.config)
        for key in ("a","b"):
            job=dict(self.job,id=key)
            self.db.execute("INSERT INTO jobs(id,spec) VALUES(?,?)",(key,json.dumps(job)))
        self.db.commit()
        with patch.object(self.m,"request",side_effect=self.m.DownloadStop("HTTP=403")) as mock_request:
            self.m.download_all(self.db,self.config)
        self.assertEqual(mock_request.call_count,1)
        self.assertTrue((self.m.ROOT/"DETENIDO.json").exists())
        self.assertEqual(dict(self.db.execute("SELECT status,count(*) FROM jobs GROUP BY status"))["pendiente"],1)
        with self.assertRaises(self.m.DownloadStop):
            self.m.download_all(self.db,self.config)


    def test_manual_dns_resume_archives_evidence_without_network(self):
        (self.directory / "original.xls").unlink()
        (self.directory / "manifest.json").unlink()
        self.m.atomic_json(self.directory / "get.http.json", {"curl_exit": 6, "http_status": "000"})
        self.m.atomic_json(self.m.ROOT / "DETENIDO.json", {"job": "fixture"})
        self.db.execute("UPDATE jobs SET status='error_descarga' WHERE id='fixture'")
        self.db.commit()
        with patch.object(self.m, "request", side_effect=AssertionError("No HTTP")):
            self.m.preparar_reanudacion_dns(self.db, self.config)
        self.assertFalse((self.m.ROOT / "DETENIDO.json").exists())
        self.assertEqual(self.db.execute("SELECT status FROM jobs").fetchone()[0], "pendiente")
        self.assertEqual(len(list((self.m.ROOT / "intentos_fallidos").rglob("get.http.json"))), 1)

    def test_manual_dns_resume_refuses_access_denial(self):
        (self.directory / "original.xls").unlink()
        (self.directory / "manifest.json").unlink()
        self.m.atomic_json(self.directory / "get.http.json", {"curl_exit": 0, "http_status": "403"})
        self.m.atomic_json(self.m.ROOT / "DETENIDO.json", {"job": "fixture"})
        self.db.execute("UPDATE jobs SET status='error_descarga' WHERE id='fixture'")
        self.db.commit()
        with self.assertRaises(self.m.DownloadStop):
            self.m.preparar_reanudacion_dns(self.db, self.config)
        self.assertTrue((self.m.ROOT / "DETENIDO.json").exists())


if __name__=="__main__":
    unittest.main()
