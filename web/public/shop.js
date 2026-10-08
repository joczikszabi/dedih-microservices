// Small helpers shared by every page. Plain JavaScript, no framework.
// The browser only ever talks to one address: the Nginx on :8080, which
// forwards /api/catalog/... to catalog and /api/orders/... to orders.

const TOKEN_KEY = "retro-shop-token";
const NAME_KEY = "retro-shop-name";
const CART_KEY = "retro-shop-cart";

export function token() {
  return localStorage.getItem(TOKEN_KEY);
}

export function saveLogin(data) {
  localStorage.setItem(TOKEN_KEY, data.access_token);
  localStorage.setItem(NAME_KEY, data.name);
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(NAME_KEY);
}

export function userName() {
  return localStorage.getItem(NAME_KEY);
}

export function huf(amount) {
  return amount.toLocaleString("en-US").replace(/,/g, " ") + " HUF";
}

// Every call to the API goes through here. Adds the token, and updates the
// "served by" line from the X-Served-By header of catalog responses.
export async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token()) headers["Authorization"] = "Bearer " + token();
  const response = await fetch(path, { ...options, headers });
  if (path.startsWith("/api/catalog/")) {
    const host = response.headers.get("X-Served-By") || "?";
    const version = response.headers.get("X-App-Version") || "?";
    const line = document.getElementById("served-by");
    if (line) line.textContent = "catalog served by " + host + ", version " + version;
  }
  let body = null;
  const text = await response.text();
  try {
    body = JSON.parse(text);
  } catch {
    body = { detail: text.slice(0, 200) };
  }
  return { status: response.status, ok: response.ok, body };
}

export function cart() {
  return JSON.parse(localStorage.getItem(CART_KEY) || "[]");
}

export function saveCart(items) {
  localStorage.setItem(CART_KEY, JSON.stringify(items));
  updateCartCount();
}

export function addToCart(product) {
  const items = cart();
  const line = items.find((i) => i.product_id === product.id);
  if (line) line.quantity += 1;
  else items.push({ product_id: product.id, name: product.name, quantity: 1, unit_price: product.price_huf });
  saveCart(items);
}

export function updateCartCount() {
  const count = cart().reduce((sum, i) => sum + i.quantity, 0);
  const el = document.getElementById("cart-count");
  if (el) el.textContent = count ? "(" + count + ")" : "";
}

export function updateHeader() {
  const el = document.getElementById("who");
  if (!el) return;
  if (token()) {
    el.innerHTML = "Logged in as <b></b> <button id='logout'>Log out</button>";
    el.querySelector("b").textContent = userName();
    el.querySelector("#logout").onclick = () => { logout(); location.href = "/"; };
  } else {
    el.innerHTML = "<a href='/login/'>Log in</a>";
  }
  updateCartCount();
}

// Text from the API goes into the page as text, never as HTML.
export function esc(value) {
  return String(value).replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";");
}
