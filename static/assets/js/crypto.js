// crypto.js
console.log("crypto.js loaded");

let aesKey = null;

/**
 * Fetch a per-conversation AES-128 key from the server.
 * Both participants derive the same key (server sorts usernames before hashing),
 * so messages encrypted by either side can be decrypted by the other.
 */
async function generateAESKey(otherUser) {
    try {
        if (!window.crypto || !window.crypto.subtle) {
            throw new Error("Web Crypto API not available in this browser");
        }

        const res = await fetch(`/conversation_key/${otherUser}`);
        if (!res.ok) throw new Error(`Server returned ${res.status} when fetching key`);

        const { key } = await res.json();

        // Convert 32-char hex string → 16 bytes
        const rawKey = new Uint8Array(key.match(/.{2}/g).map(b => parseInt(b, 16)));

        aesKey = await window.crypto.subtle.importKey(
            "raw",
            rawKey,
            { name: "AES-GCM" },
            false,              // not extractable
            ["encrypt", "decrypt"]
        );

        console.log("[DEBUG] AES key ready for conversation with", otherUser);
    } catch (err) {
        console.error("[DEBUG] Failed to load AES key:", err);
        throw err;
    }
}

/**
 * Encrypt a plaintext string using AES-GCM.
 * Returns base64-encoded ciphertext and nonce.
 */
async function encryptMessage(plaintext) {
    if (!aesKey) throw new Error("AES key not initialized — call generateAESKey first");

    const data = new TextEncoder().encode(plaintext);
    const nonce = crypto.getRandomValues(new Uint8Array(12)); // 96-bit nonce for AES-GCM

    const ciphertextBuffer = await crypto.subtle.encrypt(
        { name: "AES-GCM", iv: nonce },
        aesKey,
        data
    );

    const ciphertextB64 = btoa(String.fromCharCode(...new Uint8Array(ciphertextBuffer)));
    const nonceB64 = btoa(String.fromCharCode(...nonce));

    return { ciphertext: ciphertextB64, nonce: nonceB64 };
}

/**
 * Decrypt a base64-encoded AES-GCM message.
 */
async function decryptMessage(ciphertextB64, nonceB64) {
    if (!aesKey) throw new Error("AES key not initialized");

    const ciphertext = Uint8Array.from(atob(ciphertextB64), c => c.charCodeAt(0));
    const nonce = Uint8Array.from(atob(nonceB64), c => c.charCodeAt(0));

    const plaintextBuffer = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: nonce },
        aesKey,
        ciphertext
    );

    return new TextDecoder().decode(plaintextBuffer);
}
