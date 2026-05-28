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

    if (msg.type === "file") {
      const link = document.createElement("a");
      link.href = msg.url;
      link.textContent = "Download file";
      link.target = "_blank";
      document.getElementById("chatMessages").appendChild(link);
      return;
    }

    if (msg.type === "image") {
      const img = document.createElement("img");
      img.src = msg.url;
      img.style.maxWidth = "200px";
      document.getElementById("chatMessages").appendChild(img);
      return;
    }

    // ✅ Add audio handling here
    if (msg.type === "audio") {
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.src = msg.url;
      document.getElementById("chatMessages").appendChild(audio);
      return;
    }

    // Default: text message
    const who = msg.sender === loggedInUser ? "Me" : msg.sender;
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

      if (msg.msg_type === "text") {
        let plaintext;
        try {
          plaintext = await decryptMessage(msg.ciphertext, msg.nonce);
        } catch (err) {
          console.error("[DEBUG] Decryption failed:", err, msg);
          plaintext = "[Decryption failed]";
        }
        addMessageToUI(who, plaintext, msg.timestamp);

      } else if (msg.msg_type === "file") {
        addMessageToUI(who,
          `<a href="/uploads/${msg.file_name}" target="_blank">Download file</a>`,
          msg.timestamp);

      } else if (msg.msg_type === "image") {
        addMessageToUI(who,
          `<img src="/uploads/${msg.file_name}" style="max-width:200px;">`,
          msg.timestamp);
      } else if (msg.msg_type === "audio") {
        addMessageToUI(who,
          `<audio controls src="/uploads/${msg.file_name}"></audio>`,
          msg.timestamp);
      }
    }

  } catch (err) {
    console.error("[DEBUG] Error loading chat history:", err);
  }

  console.log("Restored chat with", user);
}

// Sidebar click → load history and set receiver
document.addEventListener("click", (e) => {
  const item = e.target.closest(".user-item");
  if (item) {
    const user = item.dataset.user;
    console.log("[DEBUG] Sidebar clicked:", item, user);
    if (user) {
      activeReceiver = user;   // <-- FIX: set receiver here
      console.log("[DEBUG] activeReceiver set to:", activeReceiver);
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

// File and image upload handlers
document.addEventListener("DOMContentLoaded", () => {
    const attachFileBtn = document.getElementById("attachFileBtn");
    const fileInput = document.getElementById("fileInput");
    const sendImageBtn = document.getElementById("sendImageBtn");
    const imageInput = document.getElementById("imageInput");
    const filePreview = document.getElementById("filePreview");

    // Attach File button → open file picker
    attachFileBtn.addEventListener("click", () => {
        console.log("[DEBUG] attachFileBtn clicked");
        if (!fileInput) {
            console.error("[DEBUG] fileInput element not found!");
            return;
        }
        fileInput.click();
    });

    fileInput.addEventListener("change", () => {
        console.log("[DEBUG] fileInput onchange triggered");
        if (fileInput.files.length > 0) {
            const file = fileInput.files[0];
            console.log("[DEBUG] Selected file:", file.name);
            // Show preview
            previewFile(file);
            // upload 
            sendFile(file);
        } else {
            console.warn("[DEBUG] No file selected");
        }
    });

    // Send Image button → open image picker
    sendImageBtn.addEventListener("click", () => {
        console.log("[DEBUG] sendImageBtn clicked");
        if (!imageInput) {
            console.error("[DEBUG] imageInput element not found!");
            return;
        }
        imageInput.click();
    });

    imageInput.addEventListener("change", () => {
        console.log("[DEBUG] imageInput onchange triggered");
        if (imageInput.files.length > 0) {
            const image = imageInput.files[0];
            console.log("[DEBUG] Selected image:", image.name);
            // Show preview
            previewFile(image);
            // upload
            sendImage(image);
        } else {
            console.warn("[DEBUG] No image selected");
        }
    });
        // Preview function
    function previewFile(file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            if (file.type.startsWith("image/")) {
                filePreview.innerHTML = `<img src="${e.target.result}" alt="${file.name}" style="max-width:150px; max-height:150px;">`;
            } else {
                filePreview.innerHTML = `<p>Selected file: ${file.name}</p>`;
            }
        };
        reader.readAsDataURL(file);
    }
});

// Audio upload handlers
document.addEventListener("DOMContentLoaded", () => {
    const sendAudioBtn = document.getElementById("sendAudioBtn");

    sendAudioBtn.addEventListener("click", () => {
        console.log("[DEBUG] sendAudioBtn clicked");
        startRecording();
    });
});

// send file to backend, get URL, render link, and notify receiver via WebSocket
function sendFile(file) {
    console.log("[DEBUG] sendFile() called with:", file);
    if (!activeReceiver) {
      console.error("[DEBUG] No activeReceiver set! Cannot upload file.");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    formData.append("receiver", activeReceiver);

    console.log("[DEBUG] FormData prepared. Receiver:", activeReceiver);

    fetch("/upload_file", { method: "POST", body: formData })
        .then(res => {
            console.log("[DEBUG] Upload response status:", res.status);
            console.log("[DEBUG] Upload response headers:", [...res.headers.entries()]);
            return res.text();  // read raw text first
        })
        .then(text => {
            console.log("[DEBUG] Raw response body:", text);
            try {
                const data = JSON.parse(text);
                console.log("[DEBUG] Parsed JSON:", data);

                if (data.url.endsWith(".pdf")) {
                  // PDF → open in new tab and render inline
                  addMessageToUI("Me", `<a href="${data.url}" target="_blank">Open PDF</a>`, new Date().toISOString());
                } else {
                  // Other files → download
                  addMessageToUI("Me", `<a href="${data.url}" target="_blank">Download file</a>`, new Date().toISOString());
                }

                // Send to receiver via WebSocket
                socket.send(JSON.stringify({
                    type: "file",
                    sender: loggedInUser,
                    receiver: activeReceiver,
                    url: data.url
                }));
            } catch (err) {
                console.error("[DEBUG] Failed to parse JSON:", err);
            }
        })
        .catch(err => console.error("[DEBUG] Upload error:", err));
}

// sendimages. Backend returns URL, we render the image and notify receiver.
function sendImage(image) {
    console.log("[DEBUG] sendImage() called with:", image);
    if (!activeReceiver) {
      console.error("[DEBUG] No activeReceiver set! Cannot upload image.");
      return;
    }

    const formData = new FormData();
    formData.append("image", image);
    formData.append("receiver", activeReceiver);

    console.log("[DEBUG] FormData prepared. Receiver:", activeReceiver);

    fetch("/upload_image", { method: "POST", body: formData })
        .then(res => {
            console.log("[DEBUG] Upload response status:", res.status);
            console.log("[DEBUG] Upload response headers:", [...res.headers.entries()]);
            return res.text();  // read raw text first
        })
        .then(text => {
            console.log("[DEBUG] Raw response body:", text);
            try {
                const data = JSON.parse(text);
                console.log("[DEBUG] Parsed JSON:", data);

                // Render immediately for sender (aligned right)
                addMessageToUI("Me", `<img src="${data.url}" style="max-width:200px;">`, new Date().toISOString());

                socket.send(JSON.stringify({
                    type: "image",
                    sender: loggedInUser,
                    receiver: activeReceiver,
                    url: data.url
                }));
                console.log("[DEBUG] WebSocket message sent for image:", data.url);
            } catch (err) {
                console.error("[DEBUG] Failed to parse JSON:", err);
            }
        })
        .catch(err => console.error("[DEBUG] Upload error:", err));
}

let mediaRecorder;
let audioChunks = [];
let isRecording = false;

const audioBtn = document.getElementById("sendAudioBtn");

audioBtn.addEventListener("click", () => {
    if (!isRecording) {
        startRecording();
        audioBtn.textContent = "⏹ Stop"; // change icon/text
    } else {
        stopRecording();
        audioBtn.textContent = "🎤 Record"; // reset icon/text
    }
    isRecording = !isRecording;
});

function startRecording() {
    navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.start();
            audioChunks = [];

            mediaRecorder.ondataavailable = e => audioChunks.push(e.data);

            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                sendAudio(audioBlob);
            };

            // Optional: auto‑stop after 60s max
            setTimeout(() => {
                if (isRecording) {
                    stopRecording();
                    audioBtn.textContent = "🎤 Record";
                    isRecording = false;
                }
            }, 60000);
        })
        .catch(err => console.error("Microphone error:", err));
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
    }
}

// Send audio blob to backend, get URL, render audio player, and notify receiver via WebSocket
function sendAudio(audioBlob) {
    console.log("[DEBUG] sendAudio() called with:", audioBlob);
    if (!activeReceiver) {
        console.error("[DEBUG] No activeReceiver set! Cannot upload audio.");
        return;
    }

    const formData = new FormData();
    formData.append("audio", audioBlob, "voiceMessage.webm");
    formData.append("receiver", activeReceiver);

    console.log("[DEBUG] FormData prepared. Receiver:", activeReceiver);

    fetch("/upload_audio", { method: "POST", body: formData })
        .then(res => {
            console.log("[DEBUG] Upload response status:", res.status);
            return res.text();
        })
        .then(text => {
            console.log("[DEBUG] Raw response body:", text);
            try {
                const data = JSON.parse(text);
                console.log("[DEBUG] Parsed JSON:", data);

                // Render immediately for sender (aligned right)
                addMessageToUI("Me", `<audio controls src="${data.url}"></audio>`, new Date().toISOString());

                // Send to receiver via WebSocket
                socket.send(JSON.stringify({
                    type: "audio",
                    sender: loggedInUser,
                    receiver: activeReceiver,
                    url: data.url
                }));
                console.log("[DEBUG] WebSocket message sent for audio:", data.url);
            } catch (err) {
                console.error("[DEBUG] Failed to parse JSON:", err);
            }
        })
        .catch(err => console.error("[DEBUG] Upload error:", err));
}

