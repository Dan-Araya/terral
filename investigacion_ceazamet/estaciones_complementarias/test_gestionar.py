"""Pruebas sintéticas y sin red. No invoca main ni descarga ni lee series de INIA."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('complementarias',Path(__file__).with_name('gestionar.py'))
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class Sheet:
    name='Datos'
    def __init__(self,rows): self.rows=rows; self.nrows=len(rows); self.ncols=5
    def cell_value(self,i,j): return self.rows[i][j]
class Book:
    def __init__(self,s): self.s=s
    def sheets(self): return [self.s]
    def release_resources(self): pass

class Tests(unittest.TestCase):
    def station(self):
        return {'e_cod':'9','xls_names':['Gabriela Mistral'],'metadata_start':'2004-02-01',
            'metadata_end':'2026-10-08','development_status':'pendiente_adquisicion',
            'sensors':[{'code':'69','label':'Temperatura del Aire','variable':'temperatura','height_m':1.5,'unit':'°C'}]}
    def fixture(self,root,rows):
        s=self.station(); j=m.plan(s)[0]
        (root/'original.xls').write_bytes(bytes.fromhex('d0cf11e0a1b11ae1')+b'sintetico')
        (root/'post.body').write_bytes(b'synthetic generation')
        m.save(root/'manifest.json',{'station':'9','fields':m.params(s,j),'sha256':m.sha(root/'original.xls'),'generation_sha256':m.sha(root/'post.body')})
        data=[['Estacion','Gabriela Mistral','','',''],['Rango','[2013-01-01,2013-01-01]','','',''],['','','','',''],
            ['Fecha',*[f'[{f}] °C Temperatura del Aire[1.5m]' for f in ['Min','Prom','Max','%Datos']]],*rows]
        return s,j,Sheet(data)
    def test_plan_partition_and_bounds(self):
        jobs=m.plan(self.station()); days=[]
        for j in jobs:
            a,b=m.scope(j['start'],j['end']); days.extend(a+m.dt.timedelta(days=i) for i in range((b-a).days+1))
        self.assertEqual(len(days),len(set(days)))
        self.assertEqual(days[0],m.LOW); self.assertEqual(days[-1],m.HIGH)
        self.assertTrue(jobs[0]['trial']); self.assertEqual(jobs[0]['start'],jobs[0]['end'])
    def test_forbidden_requests(self):
        for a,b in [('2012-12-31','2013-01-01'),('2023-12-31','2024-01-01'),('2013-01-01','2013-01-08')]:
            with self.assertRaises(ValueError): m.scope(a,b)
    def test_algarrobal_no_requests(self):
        s=self.station(); s['development_status']='sin_cobertura_en_desarrollo'
        self.assertEqual(m.plan(s),[])
    def test_zero_missing_and_external_traces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            s,j,sheet=self.fixture(root,[['2013-01-01 00:00:00',0,0,0,100],['2013-01-01 01:00:00','','','',0],['2024-01-01 00:00:00',999,999,999,100]])
            with patch.object(m,'ROOT',root),patch.object(m.xlrd,'open_workbook',return_value=Book(sheet)):
                detail,rows=m.verify(s,j,root)
            self.assertEqual(len(rows),2); self.assertEqual(rows[0]['presente'],1)
            self.assertEqual(rows[1]['presente'],0); self.assertEqual(len(detail['excluded_external_rows']),1)
            self.assertEqual(rows[0]['fila_excel'],5); self.assertEqual(rows[0]['hoja'],'Datos')
            self.assertEqual((root/'original.xls').read_bytes(),bytes.fromhex('d0cf11e0a1b11ae1')+b'sintetico')
    def test_hash_and_wrong_station_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); s,j,sheet=self.fixture(root,[])
            sheet.rows[0][1]='Otra estación'
            with patch.object(m,'ROOT',root),patch.object(m.xlrd,'open_workbook',return_value=Book(sheet)):
                with self.assertRaises(m.Invalid): m.verify(s,j,root)
            (root/'original.xls').write_bytes(b'alterado')
            with self.assertRaises(m.Invalid): m.verify(s,j,root)
    def test_empty_valid_file_not_access_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); s,j,sheet=self.fixture(root,[])
            with patch.object(m,'ROOT',root),patch.object(m.xlrd,'open_workbook',return_value=Book(sheet)):
                detail,rows=m.verify(s,j,root)
            self.assertEqual(detail['status'],'verificado_sin_observaciones'); self.assertEqual(rows,[])
    def test_absent_sensor_is_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); s,j,sheet=self.fixture(root,[])
            s['sensors'].append({'code':'70','label':'Humedad Relativa','variable':'humedad','height_m':1.5,'unit':'%'})
            j['sensors'].append('70')
            manifest=m.read(root/'manifest.json'); manifest['fields']=m.params(s,j); m.save(root/'manifest.json',manifest)
            with patch.object(m,'ROOT',root),patch.object(m.xlrd,'open_workbook',return_value=Book(sheet)):
                detail,_=m.verify(s,j,root)
            self.assertEqual(detail['sensors_absent'],['70'])
    def test_acquisition_pauses_and_verified_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=root/'bloque'; folder.mkdir()
            station=self.station(); job=m.plan(station)[0]
            config={'pause_blocks_seconds':15,'pause_post_get_seconds':10}
            m.save(root/'ultima_solicitud.json',{'finished_epoch':995})
            def fake_request(url,directory,phase,config,*args):
                data=(b'https://www.ceazamet.cl/temp/test.xls' if phase=='post' else bytes.fromhex('d0cf11e0a1b11ae1'))
                (directory/f'{phase}.body').write_bytes(data)
                return data,{'finished_epoch':1000,'finished_utc':'2026-10-09T00:00:00+00:00'}
            with patch.object(m,'ROOT',root),patch.object(m.time,'time',return_value=1000),patch.object(m.time,'sleep') as sleep,patch.object(m,'request',side_effect=fake_request) as request,patch.object(m,'verify',return_value=({},[])):
                m.acquire(station,job,folder,config)
                self.assertEqual([x.args[0] for x in sleep.call_args_list],[10,10])
                self.assertEqual(request.call_count,2)
                m.acquire(station,job,folder,config)
                self.assertEqual(request.call_count,2)
    def test_previous_retry_after_blocks_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'post.body').write_bytes(b'link')
            (root/'post.headers').write_text('HTTP/1.1 200\nRetry-After: 60\n')
            m.save(root/'post.http.json',{'curl_exit':0,'http_status':'200','body_sha256':m.sha(root/'post.body')})
            with self.assertRaises(m.Stop): m.saved_http(root,'post')
    def test_report_support_excludes_duplicates_and_reads_only_years(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'complementarias'; root.mkdir()
            station=self.station(); station.update(slug='prueba',name='Prueba',basic_sensors=['69'],pressure_reference='sensor_ausente')
            job=m.plan(station)[0]; folder=root/'prueba'/'originales'/job['id']; folder.mkdir(parents=True)
            station0,job0,sheet=self.fixture(folder,[['2013-01-01 00:00:00',0,0,0,100],['2013-01-01 00:00:00',0,0,0,100],['2013-01-01 01:00:00',1,1,1,100]])
            source=root.parent/'historico_inia'/'derivados'; source.mkdir(parents=True)
            fields=['fecha_sin_zona','dentro_periodo','variable','prom','porcentaje_datos','prom_utilizable_revision']
            for year in range(2013,2024):
                rs=[]
                if year==2013:
                    rs=[dict(zip(fields,[f'2013-01-01 {hour:02}:00:00','1','temperatura','0','100','1'])) for hour in [0,1]]
                m.write_csv(source/f'observaciones_{year}.csv',rs,fields)
            with patch.object(m,'ROOT',root),patch.object(m.xlrd,'open_workbook',return_value=Book(sheet)):
                m.report({'stations':[station],'basic_predictors':['temperatura']})
            target=root/'prueba'/'derivados'
            info=m.read(target/'compatibilidad.json')
            self.assertEqual(info['shared_basic_hours'],1)
            self.assertEqual(len(info['inia_sources']),11)
            self.assertFalse(info['physical_alignment_confirmed'])
            with (target/'soporte_comparaciones.csv').open() as f:
                rows=list(m.csv.DictReader(f))
            self.assertEqual({r['fecha_sin_zona'] for r in rows},{'2013-01-01 01:00:00'})
            with (target/'huecos.csv').open() as f:
                kinds={r['tipo'] for r in m.csv.DictReader(f)}
            self.assertIn('duplicado',kinds); self.assertIn('pendiente',kinds)
    def retry_fixture(self,root):
        station=self.station(); station['slug']='prueba'
        job=m.plan(station)[0]
        folder=root/'prueba'/'originales'/job['id']; folder.mkdir(parents=True)
        url='https://www.ceazamet.cl/index.php?e_cod=9'
        m.save(folder/'post.http.json',{'curl_exit':7,'http_status':'000','body_sha256':None,'url':url})
        (folder/'post.headers').write_text('')
        (folder/'parametros.multipart').write_bytes(b'synthetic multipart')
        m.save(folder/'adquisicion.json',{'station':'9','fields':m.params(station,job),'form_url':url})
        m.save(root/'DETENIDO.json',{'station':'prueba','job':job['id'],'status':'solicitud_fallida'})
        m.save(root/'prueba'/'estado.json',{job['id']:{'status':'solicitud_fallida'}})
        return station,job,folder
    def test_manual_retry_archives_evidence_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); station,job,folder=self.retry_fixture(root)
            before={p.name:m.sha(p) for p in folder.iterdir()}
            marker=m.sha(root/'DETENIDO.json')
            with patch.object(m,'ROOT',root),patch.object(m.subprocess,'run') as request,patch('builtins.print'):
                m.prepare_connection_retry({'stations':[station]})
                request.assert_not_called()
            self.assertFalse((root/'DETENIDO.json').exists()); self.assertFalse(folder.exists())
            archives=list((root/'prueba'/'intentos_fallidos'/job['id']).iterdir()); self.assertEqual(len(archives),1)
            self.assertEqual(m.sha(archives[0]/'DETENIDO.json'),marker)
            self.assertEqual({p.name:m.sha(p) for p in (archives[0]/'bloque').iterdir()},before)
            self.assertEqual(m.read(root/'prueba'/'estado.json')[job['id']]['status'],'pendiente')
    def test_dns_failure_can_be_archived_locally_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); station,job,folder=self.retry_fixture(root)
            info=m.read(folder/'post.http.json'); info['curl_exit']=6; m.save(folder/'post.http.json',info)
            before={p.name:m.sha(p) for p in folder.iterdir()}
            with patch.object(m,'ROOT',root),patch.object(m.subprocess,'run') as request,patch('builtins.print'):
                archive=m.prepare_connection_retry({'stations':[station]})
                request.assert_not_called()
            self.assertEqual({p.name:m.sha(p) for p in (archive/'bloque').iterdir()},before)
            self.assertFalse((root/'DETENIDO.json').exists())
            self.assertEqual(m.read(root/'prueba'/'estado.json')[job['id']]['status'],'pendiente')
            self.assertIn('curl 6',m.read(archive/'auditoria.json')['reason'])
    def test_post_reset_without_response_is_archived_but_partial_response_is_refused(self):
        for mode in ['no_response','body','http_200','headers']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); station,job,folder=self.retry_fixture(root)
                info=m.read(folder/'post.http.json'); info['curl_exit']=56
                if mode=='body':
                    (folder/'post.body').write_bytes(b'partial'); info['body_sha256']=m.sha(folder/'post.body')
                elif mode=='http_200': info['http_status']='200'
                elif mode=='headers': (folder/'post.headers').write_text('Retry-After: 60')
                m.save(folder/'post.http.json',info)
                before={p.name:m.sha(p) for p in folder.iterdir()}
                with patch.object(m,'ROOT',root),patch.object(m.subprocess,'run') as request,patch('builtins.print'):
                    if mode=='no_response':
                        archive=m.prepare_connection_retry({'stations':[station]})
                        self.assertFalse((root/'DETENIDO.json').exists())
                        self.assertEqual({p.name:m.sha(p) for p in (archive/'bloque').iterdir()},before)
                    else:
                        with self.assertRaises(m.Stop): m.prepare_connection_retry({'stations':[station]})
                        self.assertTrue((root/'DETENIDO.json').exists()); self.assertTrue(folder.exists())
                    request.assert_not_called()
    def test_manual_retry_refuses_server_responses_and_existing_download(self):
        for mode in ['429','retry_after','download']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); station,job,folder=self.retry_fixture(root)
                if mode=='429':
                    info=m.read(folder/'post.http.json'); info['http_status']='429'; m.save(folder/'post.http.json',info)
                elif mode=='retry_after': (folder/'post.headers').write_text('Retry-After: 60')
                else: (folder/'original.xls').write_bytes(b'original')
                before=m.sha(root/'DETENIDO.json')
                with patch.object(m,'ROOT',root),patch.object(m.subprocess,'run') as request:
                    with self.assertRaises(m.Stop): m.prepare_connection_retry({'stations':[station]})
                    request.assert_not_called()
                self.assertEqual(m.sha(root/'DETENIDO.json'),before)
                self.assertTrue(folder.exists()); self.assertFalse((root/'prueba'/'intentos_fallidos').exists())
    def transfer_fixture(self,root):
        station,job,folder=self.retry_fixture(root)
        form='https://www.ceazamet.cl/index.php?pag=mod_estacion&pag2=mod_estacion_descargas&e_cod=9&p_cod=ceazamet'
        link='https://www.ceazamet.cl/temp/test.xls'
        acquisition=m.read(folder/'adquisicion.json'); acquisition['form_url']=form; m.save(folder/'adquisicion.json',acquisition)
        (folder/'post.body').write_bytes(link.encode())
        (folder/'post.headers').write_text('HTTP/2 200\n')
        m.save(folder/'post.http.json',{'curl_exit':0,'http_status':'200','body_sha256':m.sha(folder/'post.body'),'url':form})
        (folder/'get.body').write_bytes(bytes.fromhex('d0cf11e0a1b11ae1')+b'partial')
        (folder/'get.headers').write_text('HTTP/2 200\ncontent-length: 100\ncontent-type: application/vnd.ms-excel\n')
        m.save(folder/'get.http.json',{'curl_exit':56,'http_status':'200','body_sha256':m.sha(folder/'get.body'),'url':link})
        return station,job,folder
    def test_transfer_retry_preserves_partial_and_post_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); station,job,folder=self.transfer_fixture(root)
            before={p.name:m.sha(p) for p in folder.iterdir()}
            with patch.object(m,'ROOT',root),patch.object(m.subprocess,'run') as request,patch('builtins.print'):
                archive=m.prepare_transfer_retry({'stations':[station]})
                request.assert_not_called()
            self.assertEqual({p.name:m.sha(p) for p in (archive/'bloque').iterdir()},before)
            self.assertFalse((root/'DETENIDO.json').exists())
            self.assertFalse(folder.exists())
            self.assertEqual(m.read(root/'prueba'/'estado.json')[job['id']]['status'],'pendiente')
            review=m.read(archive/'auditoria.json')['review']
            self.assertEqual(review['received_bytes'],15); self.assertEqual(review['missing_bytes'],85)
            self.assertFalse(review['accepted_as_observations'])
    def test_transfer_retry_refuses_limits_unknown_sizes_and_altered_files(self):
        for mode in ['429','retry_after','challenge','length_missing','length_complete','altered','original','wrong_link','wrong_period']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); station,job,folder=self.transfer_fixture(root)
                info=m.read(folder/'get.http.json')
                if mode=='429': info['http_status']='429'
                elif mode=='retry_after': (folder/'get.headers').write_text('content-length: 100\nRetry-After: 60')
                elif mode=='challenge': (folder/'get.headers').write_text('content-length: 100\ncf-mitigated: challenge')
                elif mode=='length_missing': (folder/'get.headers').write_text('HTTP/2 200')
                elif mode=='length_complete': (folder/'get.headers').write_text('content-length: 15')
                elif mode=='altered': (folder/'get.body').write_bytes(b'changed')
                elif mode=='original': (folder/'original.xls').write_bytes(b'original')
                elif mode=='wrong_link': info['url']='https://www.ceazamet.cl/temp/other.xls'
                elif mode=='wrong_period':
                    acquisition=m.read(folder/'adquisicion.json'); acquisition['fields'][0][1]='8'; m.save(folder/'adquisicion.json',acquisition)
                m.save(folder/'get.http.json',info)
                before=m.sha(root/'DETENIDO.json')
                with patch.object(m,'ROOT',root),patch.object(m.subprocess,'run') as request:
                    with self.assertRaises(m.Stop): m.prepare_transfer_retry({'stations':[station]})
                    request.assert_not_called()
                self.assertEqual(m.sha(root/'DETENIDO.json'),before); self.assertTrue(folder.exists())
                self.assertFalse((root/'prueba'/'intentos_fallidos').exists())
    def wrong_response_fixture(self,root):
        station,job,folder=self.transfer_fixture(root)
        get=m.read(folder/'get.http.json'); get['curl_exit']=0; m.save(folder/'get.http.json',get)
        (folder/'original.xls').write_bytes((folder/'get.body').read_bytes())
        manifest=m.read(folder/'adquisicion.json')
        manifest.update(download_url=get['url'],sha256=m.sha(folder/'original.xls'),generation_sha256=m.sha(folder/'post.body'))
        m.save(folder/'manifest.json',manifest)
        marker=m.read(root/'DETENIDO.json'); marker.update(status='archivo_invalido',cause='Estación XLS inesperada'); m.save(root/'DETENIDO.json',marker)
        sheet=Sheet([['Estación:','Otra estación','','',''],['Fechas:','[2025-01-01,2025-12-31]','','','']])
        return station,job,folder,sheet
    def test_wrong_response_archive_reads_metadata_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); station,job,folder,sheet=self.wrong_response_fixture(root)
            before={p.name:m.sha(p) for p in folder.iterdir()}
            original_cell=sheet.cell_value
            def metadata_only(i,j):
                if i>1: raise AssertionError('Observación reservada examinada')
                return original_cell(i,j)
            with patch.object(m,'ROOT',root),patch.object(m.xlrd,'open_workbook',return_value=Book(sheet)),patch.object(sheet,'cell_value',side_effect=metadata_only),patch.object(m.subprocess,'run') as request,patch('builtins.print'):
                archive=m.prepare_wrong_response_retry({'stations':[station]})
                request.assert_not_called()
            self.assertEqual({p.name:m.sha(p) for p in (archive/'bloque').iterdir()},before)
            review=m.read(archive/'auditoria.json')['review']
            self.assertFalse(review['observation_rows_examined']); self.assertFalse(review['accepted_as_observations'])
            self.assertEqual(m.read(root/'prueba'/'estado.json')[job['id']]['status'],'pendiente')
    def test_wrong_response_retry_refuses_matching_files_limits_and_changes(self):
        for mode in ['matches','429','retry_after','challenge','altered','fields']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); station,job,folder,sheet=self.wrong_response_fixture(root)
                if mode=='matches':
                    sheet.rows[0][1]='Gabriela Mistral'; sheet.rows[1][1]='[2013-01-01,2013-01-01]'
                elif mode=='429':
                    info=m.read(folder/'get.http.json'); info['http_status']='429'; m.save(folder/'get.http.json',info)
                elif mode=='retry_after': (folder/'get.headers').write_text('Retry-After: 60')
                elif mode=='challenge': (folder/'post.headers').write_text('cf-mitigated: challenge')
                elif mode=='altered': (folder/'original.xls').write_bytes(b'changed')
                elif mode=='fields':
                    manifest=m.read(folder/'manifest.json'); manifest['fields'][0][1]='8'; m.save(folder/'manifest.json',manifest)
                before=m.sha(root/'DETENIDO.json')
                with patch.object(m,'ROOT',root),patch.object(m.xlrd,'open_workbook',return_value=Book(sheet)),patch.object(m.subprocess,'run') as request:
                    with self.assertRaises(m.Stop): m.prepare_wrong_response_retry({'stations':[station]})
                    request.assert_not_called()
                self.assertEqual(m.sha(root/'DETENIDO.json'),before); self.assertTrue(folder.exists())
                self.assertFalse((root/'prueba'/'intentos_fallidos').exists())
    def test_ctrl_c_during_local_verification_does_not_mark_http_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); station,job,folder=self.retry_fixture(root)
            (root/'DETENIDO.json').unlink(); (folder/'manifest.json').write_text('{}')
            previous={'status':'verificado_con_observaciones','sha256':'previous'}
            m.save(root/'prueba'/'estado.json',{job['id']:previous})
            with patch.object(m,'ROOT',root),patch.object(m,'verify',side_effect=KeyboardInterrupt),patch.object(m.subprocess,'run') as request,patch('builtins.print'):
                m.run({'stations':[station]},'descargar')
                request.assert_not_called()
            self.assertFalse((root/'DETENIDO.json').exists())
            self.assertEqual(m.read(root/'prueba'/'estado.json')[job['id']],previous)
            self.assertIn('interrupcion_usuario',(root/'prueba'/'avance.jsonl').read_text())
    def local_recovery_fixture(self,root):
        station,job,folder,_=self.wrong_response_fixture(root)
        stopped=m.read(root/'DETENIDO.json'); stopped.update(status='solicitud_fallida',cause=''); m.save(root/'DETENIDO.json',stopped)
        sheet=Sheet([['Estacion','Gabriela Mistral','','',''],['Rango','[2013-01-01,2013-01-01]','','',''],['','','','',''],
            ['Fecha',*[f'[{f}] °C Temperatura del Aire[1.5m]' for f in ['Min','Prom','Max','%Datos']]]])
        return station,job,folder,sheet
    def test_local_interruption_recovery_keeps_original_and_uses_no_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); station,job,folder,sheet=self.local_recovery_fixture(root)
            before=m.sha(folder/'original.xls'); stopped_hash=m.sha(root/'DETENIDO.json')
            with patch.object(m,'ROOT',root),patch.object(m.xlrd,'open_workbook',return_value=Book(sheet)),patch.object(m.subprocess,'run') as request,patch('builtins.print'):
                archive=m.recover_local_interruption({'stations':[station]})
                request.assert_not_called()
            self.assertEqual(m.sha(folder/'original.xls'),before)
            self.assertEqual(m.sha(archive/'DETENIDO.json'),stopped_hash)
            self.assertEqual(m.read(root/'prueba'/'estado.json')[job['id']]['status'],'verificado_sin_observaciones')
            self.assertFalse((root/'DETENIDO.json').exists())
    def test_local_recovery_refuses_invalid_file_or_real_http_failure(self):
        for mode in ['wrong_station','http_failure','altered']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); station,job,folder,sheet=self.local_recovery_fixture(root)
                if mode=='wrong_station': sheet.rows[0][1]='Otra estación'
                elif mode=='http_failure':
                    info=m.read(folder/'get.http.json'); info['http_status']='429'; m.save(folder/'get.http.json',info)
                else: (folder/'original.xls').write_bytes(b'changed')
                before=m.sha(root/'DETENIDO.json')
                with patch.object(m,'ROOT',root),patch.object(m.xlrd,'open_workbook',return_value=Book(sheet)),patch.object(m.subprocess,'run') as request:
                    with self.assertRaises((m.Stop,m.Invalid)): m.recover_local_interruption({'stations':[station]})
                    request.assert_not_called()
                self.assertEqual(m.sha(root/'DETENIDO.json'),before)
    def test_request_no_retry_on_429(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def fake(command,**kwargs):
                (root/'post.body').write_bytes(b'limit'); (root/'post.headers').write_text('HTTP/1.1 429\nRetry-After: 60\n')
                return m.subprocess.CompletedProcess(command,0,'429','')
            with patch.object(m,'ROOT',root),patch.object(m.subprocess,'run',side_effect=fake) as run:
                with self.assertRaises(m.Stop): m.request('https://www.ceazamet.cl/index.php?e_cod=9',root,'post',{})
                self.assertEqual(run.call_count,1)
            self.assertTrue((root/'post.body').exists()); self.assertTrue((root/'post.http.json').exists())

if __name__=='__main__': unittest.main()
