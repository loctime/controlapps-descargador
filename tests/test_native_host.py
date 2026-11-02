import io
import json
import os
import struct
import subprocess
import sys
import time

from descargador import native_host as nh


def _trama(obj):
    datos = json.dumps(obj).encode("utf-8")
    return struct.pack("<I", len(datos)) + datos


def _respuestas(salida):
    salida.seek(0)
    out = []
    while True:
        cab = salida.read(4)
        if not cab:
            return out
        out.append(json.loads(salida.read(struct.unpack("<I", cab)[0])))


def test_add_deja_pedido_en_inbox_y_abre_la_app_si_no_corre(tmp_path):
    abiertas = []
    resp = nh.procesar({"type": "add", "url": "https://youtu.be/abc", "inicio": 10, "fin": 25, "modo": "mp3"},
                       inbox=str(tmp_path / "inbox"), latido=str(tmp_path / "no-existe"),
                       abrir=lambda: abiertas.append(1))
    assert resp["ok"] and resp["queued"] and resp["app_started"]
    assert abiertas == [1]
    assert nh.tomar_pedidos(str(tmp_path / "inbox")) == [
        {"url": "https://youtu.be/abc", "inicio": 10, "fin": 25, "modo": "mp3"}]
    assert nh.tomar_pedidos(str(tmp_path / "inbox")) == []  # se consumen una sola vez


def test_add_no_abre_la_app_si_el_latido_es_reciente(tmp_path):
    latido = tmp_path / "app.alive"
    nh.marcar_viva(str(latido))
    abiertas = []
    resp = nh.procesar({"type": "add", "url": "https://youtu.be/abc"}, inbox=str(tmp_path / "i"),
                       latido=str(latido), abrir=lambda: abiertas.append(1))
    assert resp["ok"] and not resp["app_started"] and abiertas == []


def test_latido_viejo_cuenta_como_app_cerrada(tmp_path):
    latido = tmp_path / "app.alive"
    nh.marcar_viva(str(latido))
    assert nh.app_corriendo(str(latido))
    assert not nh.app_corriendo(str(latido), ahora=time.time() + 60)


def test_pedidos_invalidos_se_rechazan(tmp_path):
    for msg, error in [
        ({"type": "add", "url": "file:///C:/secreto"}, "url_invalida"),
        ({"type": "add", "url": "javascript:alert(1)"}, "url_invalida"),
        ({"type": "add", "url": 5}, "url_invalida"),
        ({"type": "add", "url": "https://x.com/v", "inicio": 30, "fin": 10}, "rango_invalido"),
        ({"type": "add", "url": "https://x.com/v", "inicio": 5}, "rango_invalido"),
        ({"type": "add", "url": "https://x.com/v", "modo": "zip"}, "modo_invalido"),
        ({"type": "borrar"}, "tipo_desconocido"),
    ]:
        resp = nh.procesar(msg, inbox=str(tmp_path / "i"), latido=str(tmp_path / "x"), abrir=lambda: None)
        assert not resp["ok"] and resp["error"] == error, msg
    assert not (tmp_path / "i").exists()


def test_tomar_pedidos_descarta_archivos_corruptos(tmp_path):
    inbox = tmp_path / "inbox"; inbox.mkdir()
    (inbox / "1.json").write_text("{no es json", encoding="utf-8")
    (inbox / "2.json").write_text(json.dumps({"url": "ftp://x/y"}), encoding="utf-8")
    (inbox / "3.json").write_text(json.dumps({"url": "https://x.com/v"}), encoding="utf-8")
    assert nh.tomar_pedidos(str(inbox)) == [{"url": "https://x.com/v"}]
    assert os.listdir(inbox) == []


def test_servir_responde_cada_mensaje_con_el_protocolo_de_chrome(tmp_path):
    entrada = io.BytesIO(_trama({"type": "ping"}) + _trama({"type": "add", "url": "https://x.com/v"}))
    salida = io.BytesIO()
    codigo = nh.servir(entrada, salida, inbox=str(tmp_path / "i"), latido=str(tmp_path / "x"), abrir=lambda: None)
    ping, add = _respuestas(salida)
    assert codigo == 0
    assert ping["ok"] and ping["protocol"] == nh.PROTOCOL and ping["version"]
    assert add["ok"] and add["queued"]


def test_manifest_solo_autoriza_a_la_extension():
    manifest = nh.construir_manifest(r"C:\app\host.exe")
    assert manifest["name"] == nh.HOST_NAME and manifest["type"] == "stdio"
    assert manifest["allowed_origins"] == [f"chrome-extension://{i}/" for i in nh.EXTENSION_IDS]


def test_el_id_del_host_coincide_con_la_key_del_manifest_de_la_extension():
    import base64, hashlib
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "extension", "manifest.json"), encoding="utf-8") as f:
        key = json.load(f)["key"]
    digest = hashlib.sha256(base64.b64decode(key)).hexdigest()[:32]
    assert "".join(chr(ord("a") + int(c, 16)) for c in digest) in nh.EXTENSION_IDS


def test_host_como_proceso_real_habla_el_protocolo(tmp_path):
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, USERPROFILE=str(tmp_path), HOME=str(tmp_path))
    proc = subprocess.run([sys.executable, os.path.join(raiz, "host_main.py")],
                          input=_trama({"type": "ping"}), capture_output=True, env=env, timeout=30,
                          cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr.decode()
    (resp,) = _respuestas(io.BytesIO(proc.stdout))
    assert resp["ok"] and resp["app_running"] is False
