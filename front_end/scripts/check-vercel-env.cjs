// Valida a configuração antes do build remoto.
const valor = process.env.EXPO_PUBLIC_API_URL?.trim();

function falhar(mensagem) {
  console.error(`[Vercel] ${mensagem}`);
  process.exit(1);
}

if (!valor) {
  falhar("Configure EXPO_PUBLIC_API_URL no projeto Vercel.");
}

let url;

try {
  url = new URL(valor);
} catch {
  falhar("EXPO_PUBLIC_API_URL precisa ser uma URL HTTPS válida.");
}

if (
  url.protocol !== "https:" ||
  url.username ||
  url.password ||
  url.search ||
  url.hash
) {
  falhar("Use HTTPS, sem credenciais, query ou fragmento.");
}

const host = url.hostname.toLowerCase();

const ipv4 = /^\d+\.\d+\.\d+\.\d+$/.test(host)
  ? host.split(".").map(Number)
  : null;

const privado =
  ipv4 &&
  (ipv4[0] === 0 ||
    ipv4[0] === 10 ||
    ipv4[0] === 127 ||
    (ipv4[0] === 169 && ipv4[1] === 254) ||
    (ipv4[0] === 172 && ipv4[1] >= 16 && ipv4[1] <= 31) ||
    (ipv4[0] === 192 && ipv4[1] === 168));

if (
  privado ||
  host === "localhost" ||
  host === "[::1]" ||
  host.endsWith(".localhost") ||
  host.endsWith(".local")
) {
  falhar("Informe o endereço público do backend.");
}

console.log("[Vercel] URL do backend validada.");
