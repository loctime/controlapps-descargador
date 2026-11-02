const $ = (id) => document.getElementById(id);
let tab = null;

function mostrar(texto, clase = "") {
  $("estado").textContent = texto;
  $("estado").className = clase;
}

// Lee el reproductor de la pestana (YouTube, Instagram, etc.). activeTab alcanza
// porque el popup se abrio por un clic del usuario.
async function leerReproductor() {
  try {
    const [resultado] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const v = document.querySelector("video");
        return v ? { actual: v.currentTime, duracion: v.duration } : null;
      },
    });
    return resultado && resultado.result;
  } catch (e) {
    return null; // pagina sin permiso (chrome://, tienda, etc.)
  }
}

async function iniciar() {
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  $("titulo").textContent = tab.title || tab.url;
  const reproductor = await leerReproductor();
  if (!reproductor) {
    $("recorte").hidden = true;
  } else if (isFinite(reproductor.duracion) && reproductor.duracion > 0) {
    $("duracion").textContent = `de ${formatoTiempo(reproductor.duracion)}`;
  }
  const estado = await hablarConApp({ type: "ping" });
  if (!estado.ok) {
    mostrar(textoError(estado), "error");
    $("enviar").disabled = true;
  }
}

async function usarTiempoActual(campo) {
  const reproductor = await leerReproductor();
  if (reproductor) $(campo).value = formatoTiempo(reproductor.actual);
}

$("usar-inicio").addEventListener("click", () => usarTiempoActual("inicio"));
$("usar-fin").addEventListener("click", () => usarTiempoActual("fin"));

$("enviar").addEventListener("click", async () => {
  const mensaje = { type: "add", url: tab.url };
  const modo = $("modo").value;
  if (modo) mensaje.modo = modo;

  const textoInicio = $("inicio").value.trim();
  const textoFin = $("fin").value.trim();
  if (textoInicio || textoFin) {
    const inicio = textoInicio ? parseTiempo(textoInicio) : 0;
    const fin = parseTiempo(textoFin);
    if (inicio === null || fin === null || fin <= inicio) {
      mostrar(textoError({ error: "rango_invalido" }), "error");
      return;
    }
    mensaje.inicio = inicio;
    mensaje.fin = fin;
  }

  $("enviar").disabled = true;
  const respuesta = await hablarConApp(mensaje);
  $("enviar").disabled = false;
  if (respuesta.ok) {
    mostrar(respuesta.app_started ? "Enviado. Abriendo el Descargador…" : "Agregado a la cola.", "ok");
  } else {
    mostrar(textoError(respuesta), "error");
  }
});

iniciar();
