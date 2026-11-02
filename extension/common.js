// Comunicacion con el host nativo (lo instala el instalador del Descargador).
const HOST = "com.controlapps.descargador";

function hablarConApp(mensaje) {
  return new Promise((resolve) => {
    chrome.runtime.sendNativeMessage(HOST, mensaje, (respuesta) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: "sin_host", detalle: chrome.runtime.lastError.message });
      } else {
        resolve(respuesta || { ok: false, error: "sin_respuesta" });
      }
    });
  });
}

const MENSAJES_ERROR = {
  sin_host: "No encuentro el Descargador. Instalalo (o reinstalalo) y probá de nuevo.",
  url_invalida: "Este enlace no se puede descargar.",
  rango_invalido: "El rango no es válido: Fin tiene que ser mayor que Inicio.",
  modo_invalido: "Modo de descarga desconocido.",
  tipo_desconocido: "La app y la extensión tienen versiones distintas. Actualizá el Descargador.",
};

function textoError(respuesta) {
  return MENSAJES_ERROR[respuesta.error] || `Error: ${respuesta.error || "desconocido"}`;
}

// "90", "1:30" o "1:02:03" -> segundos; null si no se entiende.
function parseTiempo(texto) {
  const partes = String(texto).trim().split(":");
  if (partes.length < 1 || partes.length > 3 || !partes.every((p) => /^\d+$/.test(p.trim()))) return null;
  return partes.reduce((total, p) => total * 60 + parseInt(p, 10), 0);
}

function formatoTiempo(segundos) {
  segundos = Math.max(0, Math.floor(segundos));
  const h = Math.floor(segundos / 3600);
  const m = Math.floor((segundos % 3600) / 60);
  const s = segundos % 60;
  const dos = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${dos(m)}:${dos(s)}` : `${dos(m)}:${dos(s)}`;
}
