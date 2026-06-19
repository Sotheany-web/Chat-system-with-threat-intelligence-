// crypto.js
console.log("crypto.js loaded");

// Per-conversation key cache: { username -> CryptoKey }
const _aesKeyMap = {};
let aesKey = null; // points to the active conversation's key (backward compat)

async function generateAESKey(otherUser) {
    try {
        if (!window.crypto || !window.crypto.subtle) {
            throw new Error("Web Crypto API not available in this browser");
        }

        // Return cached key if available
        if (_aesKeyMap[otherUser]) {
            aesKey = _aesKeyMap[otherUser];
            return;
        }

        const res = await fetch(`/conversation_key/${otherUser}`);
        if (!res.ok) throw new Error(`Server returned ${res.status} when fetching key`);

        const { key } = await res.json();

        // 32-char hex → 16 bytes → AES-128-GCM key
        const rawKey = new Uint8Array(key.match(/.{2}/g).map(b => parseInt(b, 16)));

        const importedKey = await window.crypto.subtle.importKey(
            "raw",
            rawKey,
            { name: "AES-GCM" },
            false,
            ["encrypt", "decrypt"]
        );

        _aesKeyMap[otherUser] = importedKey;
        aesKey = importedKey;
        console.log("[Crypto] AES key ready for", otherUser);
    } catch (err) {
        console.error("[Crypto] Failed to load AES key for", otherUser, err);
        throw err;
    }
}

// async function encryptMessage(plaintext) {
async function encryptMessage(plaintext, otherUser = null) {
    if (otherUser && !_aesKeyMap[otherUser]) {
        await generateAESKey(otherUser);
    }

    if (!aesKey) throw new Error("AES key not initialized — call generateAESKey first");

    const data = new TextEncoder().encode(plaintext);
    const nonce = crypto.getRandomValues(new Uint8Array(12));

    const ciphertextBuffer = await crypto.subtle.encrypt(
        { name: "AES-GCM", iv: nonce },
        aesKey,
        data
    );

    const ciphertextB64 = btoa(String.fromCharCode(...new Uint8Array(ciphertextBuffer)));
    const nonceB64 = btoa(String.fromCharCode(...nonce));

    return { ciphertext: ciphertextB64, nonce: nonceB64 };
}

// fromUser: if provided, uses that conversation's key; otherwise uses the active aesKey
async function decryptMessage(ciphertextB64, nonceB64, fromUser) {
    const key = (fromUser && _aesKeyMap[fromUser]) || aesKey;
    if (!key) throw new Error("AES key not initialized" + (fromUser ? " for " + fromUser : ""));

    const ciphertext = Uint8Array.from(atob(ciphertextB64), c => c.charCodeAt(0));
    const nonce = Uint8Array.from(atob(nonceB64), c => c.charCodeAt(0));

    const plaintextBuffer = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: nonce },
        key,
        ciphertext
    );

    return new TextDecoder().decode(plaintextBuffer);
}
