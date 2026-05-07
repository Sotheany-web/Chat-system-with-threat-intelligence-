// crypto.js
console.log("crypto.js loaded");

let aesKey; // shared AES key

// Check environment
console.log("[DEBUG] window.crypto:", window.crypto);
console.log("[DEBUG] window.crypto.subtle:", window.crypto ? window.crypto.subtle : "no subtle");

// Step 1: RSA public key import (simplified demo)
async function importPublicKey(pem) {
  if (!window.crypto || !window.crypto.subtle) {
    throw new Error("Web Crypto API not available");
  }

  const binaryDer = str2ab(
    pem.replace(/-----(BEGIN|END) PUBLIC KEY-----/g, "").trim()
  );
  return await window.crypto.subtle.importKey(
    "spki",
    binaryDer,
    { name: "RSA-OAEP", hash: "SHA-256" },
    true,
    ["encrypt"]
  );
}

// Step 2: Generate AES key
async function generateAESKey() {
  try {
    if (!window.crypto || !window.crypto.subtle) {
      throw new Error("Web Crypto API not available");
    }

    // Debug: show what we're about to import
    const rawKey = new TextEncoder().encode("1234567890abcdef");
    console.log("[DEBUG] rawKey length:", rawKey.length, "bytes");

    aesKey = await window.crypto.subtle.importKey(
      "raw",
      rawKey,
      { name: "AES-GCM" },
      true,
      ["encrypt", "decrypt"]
    );

    console.log("[DEBUG] AES key generated:", aesKey);
  } catch (err) {
    console.error("[DEBUG] Failed to generate AES key:", err);
    throw err; // rethrow so caller sees it
  }
}

// Step 3: Encrypt message with AES-GCM
async function encryptMessage(plaintext) {
  const encoder = new TextEncoder();
  const data = encoder.encode(plaintext);

  // AES-GCM requires a 12-byte nonce
  const nonce = crypto.getRandomValues(new Uint8Array(12));

  const ciphertextBuffer = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce },
    aesKey,
    data
  );

  // Convert to base64 for transport
  const ciphertextB64 = btoa(String.fromCharCode(...new Uint8Array(ciphertextBuffer)));
  const nonceB64 = btoa(String.fromCharCode(...nonce));

  return { ciphertext: ciphertextB64, nonce: nonceB64 };
}

// Step 4: Decrypt message with AES-GCM
async function decryptMessage(ciphertextB64, nonceB64) {
  if (!aesKey) throw new Error("AES key not initialized");

  // Decode base64 back into bytes
  const ciphertext = Uint8Array.from(atob(ciphertextB64), c => c.charCodeAt(0));
  const nonce = Uint8Array.from(atob(nonceB64), c => c.charCodeAt(0));

  console.log("Decrypting:", { nonceLength: nonce.length, ciphertextLength: ciphertext.length });

  const plaintextBuffer = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: nonce },
    aesKey,
    ciphertext
  );

  return new TextDecoder().decode(plaintextBuffer);
}

// Helper: convert PEM to ArrayBuffer
function str2ab(str) {
  const b64 = str.replace(/\s+/g, "");
  const raw = atob(b64);
  const buffer = new ArrayBuffer(raw.length);
  const view = new Uint8Array(buffer);
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i);
  return buffer;
}
