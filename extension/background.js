importScripts("common.js");

const MENU_ID = "enviar-a-descargador";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: "Enviar a ControlApps Descargador",
    contexts: ["link", "page", "video"],
  });
});

// Avisa el resultado con el texto del icono: no necesita permiso de notificaciones.
function avisar(tabId, texto, color) {
  chrome.action.setBadgeBackgroundColor({ color, tabId });
  chrome.action.setBadgeText({ text: texto, tabId });
  setTimeout(() => chrome.action.setBadgeText({ text: "", tabId }), 3000);
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== MENU_ID) return;
  const url = info.linkUrl || info.pageUrl || (tab && tab.url);
  const respuesta = await hablarConApp({ type: "add", url });
  if (tab) avisar(tab.id, respuesta.ok ? "OK" : "!", respuesta.ok ? "#16a34a" : "#dc2626");
});
