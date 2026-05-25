console.log("chat.js loaded");

let activeReceiver = null;

const wsProtocol = window.location.protocol === "https:" ? "wss://" : "ws://";
const wsUrl = `${wsProtocol}${window.location.host}/ws`;

// --- WebSocket connection ---
let socket;
try {
    socket = new WebSocket(wsUrl);

    socket.addEventListener("open", () => {
        console.log("[DEBUG] WebSocket connected as", loggedInUser);
        socket.send(loggedInUser); // backend expects username as the first message
    });

    socket.addEventListener("error", (err) => console.error("[DEBUG] WebSocket error:", err));
    socket.addEventListener("close", (e) => console.warn("[DEBUG] WebSocket closed:", e));
} catch (err) {
    console.error("[DEBUG] Failed to create WebSocket:", err);
}

// --- On page load: restore chat if chatUser is set from URL ---
document.addEventListener("DOMContentLoaded", async () => {
    try {
        if (chatUser && chatUser !== "None") {
            await loadChatHistory(chatUser);
        }
    } catch (err) {
        console.error("[DEBUG] Failed to initialize chat:", err);
    }
});

// --- Handle incoming messages via WebSocket ---
socket.onmessage = async (event) => {
    try {
        const msg = JSON.parse(event.data);

        // Only render messages for the currently open conversation
        if (msg.sender !== activeReceiver && msg.receiver !== activeReceiver) return;

        let plaintext;
        try {
            plaintext = await decryptMessage(msg.ciphertext, msg.nonce);
        } catch (err) {
            console.error("[DEBUG] Failed to decrypt incoming message:", err, msg);
            plaintext = "[Decryption failed]";
        }

        const who = msg.sender === loggedInUser ? "Me" : msg.sender;
        addMessageToUI(who, plaintext, msg.timestamp);
    } catch (err) {
        console.error("[DEBUG] Failed to process incoming message:", err, event.data);
    }
};

// --- Load chat history for a given user ---
async function loadChatHistory(user) {
    activeReceiver = user;

    // Load conversation-specific AES key before any encrypt/decrypt
    try {
        await generateAESKey(user);
    } catch (err) {
        console.error("[DEBUG] Failed to load AES key for", user, ":", err);
        return;
    }

    // Update chat header
    document.querySelector(".currentChatName").textContent = user;
    document.querySelector(".currentChatAvatar").textContent = user[0].toUpperCase();

    // Clear previous messages
    const chatBox = document.getElementById("chatMessages");
    chatBox.innerHTML = "";

    try {
        const res = await fetch(`/messages/${user}`);
        if (!res.ok) {
            console.error("[DEBUG] Failed to fetch history:", res.status);
            return;
        }

        const history = await res.json();
        console.log("Fetched history for", user, ":", history.length, "messages");

        for (const msg of history) {
            const who = msg.sender === loggedInUser ? "Me" : msg.sender;
            let plaintext;
            try {
                plaintext = await decryptMessage(msg.ciphertext, msg.nonce);
            } catch (err) {
                console.error("[DEBUG] Decryption failed for msg:", err);
                plaintext = "[Decryption failed]";
            }
            addMessageToUI(who, plaintext, msg.timestamp);
        }
    } catch (err) {
        console.error("[DEBUG] Error loading chat history:", err);
    }
}

// --- Sidebar click → load chat history ---
document.addEventListener("click", (e) => {
    const item = e.target.closest(".user-item");
    if (item) {
        const user = item.dataset.user;
        if (user) {
            loadChatHistory(user);
        } else {
            console.warn("[DEBUG] Clicked user-item without data-user attribute");
        }
    }
});

// --- Render a message bubble in the chat box ---
function addMessageToUI(sender, content, timestamp = null) {
    const chatBox = document.getElementById("chatMessages");
    const messageDiv = document.createElement("div");
    messageDiv.className = sender === "Me" ? "message sent" : "message received";

    const time = timestamp
        ? new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        : new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    messageDiv.innerHTML = `
        <div class="message-wrapper">
            <div class="message-content">
                <div class="message-text">${content}</div>
            </div>
            <div class="message-timestamp">${time}</div>
        </div>`;

    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight; // auto-scroll to latest
}

// --- Send button: encrypt and send ---
document.getElementById("sendButton").addEventListener("click", async () => {
    const input = document.getElementById("messageInput");
    const message = input.value.trim();

    if (!message || !activeReceiver) return;

    try {
        const { ciphertext, nonce } = await encryptMessage(message);

        socket.send(JSON.stringify({
            receiver: activeReceiver,
            ciphertext,
            nonce
        }));

        addMessageToUI("Me", message, new Date().toISOString());
        input.value = "";
    } catch (err) {
        console.error("[DEBUG] Failed to send message:", err);
    }
});

// --- Enter key support ---
document.getElementById("messageInput").addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
        e.preventDefault();
        document.getElementById("sendButton").click();
    }
});
