console.log("chat.js loaded");

let activeReceiver = null;  // track who you're chatting with

const wsProtocol = window.location.protocol === "https:" ? "wss://" : "ws://";

const wsUrl = `${wsProtocol}${window.location.host}/ws`;

// WebSocket connection
let socket;
try {
  socket = new WebSocket(wsUrl);

  // Handshake: send username immediately after connecting
  socket.addEventListener("open", () => {
    console.log("[DEBUG] WebSocket connected as", loggedInUser);
    socket.send(loggedInUser); // backend expects this first
  });

  socket.addEventListener("error", (err) => console.error("[DEBUG] WebSocket error:", err));
  socket.addEventListener("close", (e) => console.warn("[DEBUG] WebSocket closed:", e));
} catch (err) {
  console.error("[DEBUG] Failed to create WebSocket:", err);
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await generateAESKey(); // ensure aesKey is ready
    const savedChatUser = localStorage.getItem("lastChatUser");
    if (savedChatUser) {
      loadChatHistory(savedChatUser);
    }
  } catch (err) {
    console.error("[DEBUG] Failed to initialize AES key:", err);
  }
});

// decrypt message before displaying
socket.onmessage = async (event) => {
  try {
    const msg = JSON.parse(event.data);
    const who = msg.sender === loggedInUser ? "Me" : msg.sender;

    // Decrypt ciphertext safely
    let plaintext;
    try {
      plaintext = await decryptMessage(msg.ciphertext, msg.nonce);
    } catch (err) {
      console.error("[DEBUG] Failed to decrypt message:", err, msg);
      plaintext = "[Decryption failed]";
    }

    addMessageToUI(who, plaintext, msg.timestamp);
  } catch (err) {
    console.error("[DEBUG] Failed to process incoming message:", err, event.data);
  }
};

// Reusable function to fetch and render history
async function loadChatHistory(user) {
  activeReceiver = user;
  localStorage.setItem("lastChatUser", user);

  // Update header
  document.querySelector(".currentChatName").textContent = user;
  document.querySelector(".currentChatAvatar").textContent = user[0].toUpperCase();

  // Clear chat window
  const chatBox = document.getElementById("chatMessages");
  chatBox.innerHTML = "";

  try {
    const res = await fetch(`/messages/${user}`);
    console.log("Fetch response status:", res.status);

    if (!res.ok) {
      console.error("[DEBUG] Failed to fetch history:", res.status);
      return;
    }

    const history = await res.json();
    console.log("Fetched history for", user, ":", history);

    for (const msg of history) {
      const who = msg.sender === loggedInUser ? "Me" : msg.sender;
      let plaintext;
      try {
        plaintext = await decryptMessage(msg.ciphertext, msg.nonce);
      } catch (err) {
        console.error("[DEBUG] Decryption failed:", err, msg);
        plaintext = "[Decryption failed]";
      }
      addMessageToUI(who, plaintext, msg.timestamp);
    }
  } catch (err) {
    console.error("[DEBUG] Error loading chat history:", err);
  }

  console.log("Restored chat with", user);
}

// Sidebar click → load history
document.addEventListener("click", (e) => {
  const item = e.target.closest(".user-item"); // find nearest parent with class
  if (item) {
    const user = item.dataset.user;
    console.log("[DEBUG] Sidebar clicked:", item, user);
    if (user) {
      loadChatHistory(user);
    } else {
      console.warn("[DEBUG] Clicked user-item without data-user attribute");
    }
  }
});


// Add message bubble to UI
function addMessageToUI(sender, content, timestamp=null) {
  const chatBox = document.getElementById("chatMessages");
  const messageDiv = document.createElement("div");
  messageDiv.className = sender === "Me" ? "message sent" : "message received";
  messageDiv.innerHTML = `
      <div class="message-wrapper">
          <div class="message-content">
              <div class="message-text">${content}</div>
          </div>
          <div class="message-timestamp">${timestamp || new Date().toLocaleTimeString()}</div>
      </div>`;
  chatBox.appendChild(messageDiv);

  // Auto-scroll to bottom like WhatsApp
  chatBox.scrollTop = chatBox.scrollHeight;
}

// Send button + encrypt the message
document.getElementById("sendButton").addEventListener("click", async () => {
  const input = document.getElementById("messageInput");
  const message = input.value.trim();

  if (message !== "" && activeReceiver) {
    try {
      // Encrypt with AES before sending
      const { ciphertext, nonce } = await encryptMessage(message);

      socket.send(JSON.stringify({
        receiver: activeReceiver,
        ciphertext,
        nonce
      }));

      // Show plaintext locally with current time
      addMessageToUI("Me", message, new Date().toISOString());
      input.value = "";
    } catch (err) {
      console.error("[DEBUG] Failed to send message:", err);
    }
  }
});

// Support Enter key
document.getElementById("messageInput").addEventListener("keypress", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    document.getElementById("sendButton").click();
  }
});

