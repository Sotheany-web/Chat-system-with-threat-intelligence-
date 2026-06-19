console.log("chat.js loaded");

let activeReceiver = null;  // track who you're chatting with

const wsProtocol = window.location.protocol === "https:" ? "wss://" : "ws://";

const wsUrl = `${wsProtocol}${window.location.host}/ws`;

//for audio/video calls 
let pc;              // RTCPeerConnection
let localStream;     // microphone stream
let callStartTime;   // for duration timer
let durationInterval;
let mediaRecorder;
let audioChunks = [];
let isRecording = false;

let videoPc;  
let localVideoStream;
let videoCallStartTime;
let videoDurationInterval;

const audioBtn = document.getElementById("sendAudioBtn");
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

const ICE_SERVERS = [
  { urls: "stun:stun.l.google.com:19302" },
  {
    urls: "turn:openrelay.metered.ca:80",
    username: "openrelayproject",
    credential: "openrelayproject"
  },
  {
    urls: "turn:openrelay.metered.ca:443",
    username: "openrelayproject",
    credential: "openrelayproject"
  },
  {
    urls: "turn:openrelay.metered.ca:443?transport=tcp",
    username: "openrelayproject",
    credential: "openrelayproject"
  }
];

function createAudioPeerConnection() {
  return new RTCPeerConnection({ iceServers: ICE_SERVERS });
}

function createVideoPeerConnection() {
  return new RTCPeerConnection({ iceServers: ICE_SERVERS });
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const savedChatUser = localStorage.getItem("lastChatUser");
    if (savedChatUser) {
      await generateAESKey(savedChatUser);
      loadChatHistory(savedChatUser);
    }
  } catch (err) {
    console.error("[DEBUG] Failed to initialize AES key:", err);
  }
});

let pendingCandidates = [];
let pendingOffer = null;
let pendingAudioCandidates = [];
let pendingVideoCandidates = [];

// decrypt message before displaying (receiver side)
socket.onmessage = async (event) => {
  try {
    const msg = JSON.parse(event.data);

    if (msg.type === "file" || msg.type === "image") {
      const _imgExts = ["jpg", "jpeg", "png", "gif", "webp"];
      const _who = msg.sender === loggedInUser ? "Me" : msg.sender;
      if (msg.type === "image") {
        addMessageToUI(_who, makeMediaNode('img', msg.url), null);
      } else {
        const _ext = (msg.url || "").split(".").pop().split("?")[0].toLowerCase();
        if (_imgExts.includes(_ext)) {
          addMessageToUI(_who, makeMediaNode('img', msg.url), null);
        } else {
          addMessageToUI(_who, makeMediaNode('file', msg.url), null);
        }
      }
      return;
    }

    // Add audio handling here
    if (msg.type === "audio") {
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.src = msg.url;
      document.getElementById("chatMessages").appendChild(audio);
      return;
    }

    // Text message + decryption
    if (msg.type === "text") {
      const chatPartner = msg.sender === loggedInUser ? msg.receiver : msg.sender;
      // Ensure we have a key for this conversation (may arrive before user opens chat)
      if (!_aesKeyMap[chatPartner]) {
        try { await generateAESKey(chatPartner); } catch (_) {}
      }
      let plaintext;
      try {
        plaintext = await decryptMessage(msg.ciphertext, msg.nonce, chatPartner);
      } catch (err) {
        console.error("[DEBUG] Failed to decrypt text message:", err, msg);
        plaintext = "[Decryption failed]";
      }
      // Only render in chat if this is the active conversation
      if (chatPartner === activeReceiver) {
        addMessageToUI(msg.sender === loggedInUser ? "Me" : msg.sender, plaintext, msg.timestamp);
      }
      return;
    }

    // Incoming call offer
    if (msg.type === "call-offer" && msg.receiver === loggedInUser) {
      console.log("[Receiver] Incoming call-offer:", msg);

      // 🔹 Show incoming call UI here
      document.getElementById("callOverlay").style.display = "flex";
      document.getElementById("incomingCallInterface").style.display = "block";
      console.log("[Receiver] Showing incoming call overlay.");

      // 🔹 Hide other interfaces so receiver doesn't see caller UI
      document.getElementById("audioCallInterface").style.display = "none";   // CHANGE
      document.getElementById("videoCallInterface").style.display = "none";   // CHANGE

      // 🔹 Populate with caller info instead of defaults
      document.getElementById("incomingCallerName").innerText = msg.sender;   // CHANGE
      document.getElementById("incomingCallPrompt").innerText = `${msg.sender} is calling...`; // CHANGE
      console.log("[Receiver] Caller info populated:", msg.sender);

      // 🔹 Set up appropriate peer connection based on call type 
      if (msg.callType === "video") {
        // Create video peer connection
        console.log("[Receiver] Setting up video peer connection.");
        videoPc = createVideoPeerConnection();

        videoPc.onconnectionstatechange = () =>
          console.log("Video connection state:", videoPc.connectionState);
        videoPc.oniceconnectionstatechange = () =>
          console.log("Video ICE state:", videoPc.iceConnectionState);

        videoPc.onicecandidate = event => {
          console.log("[Receiver] Video ICE candidate event:", event.candidate);
          if (event.candidate) {
            socket.send(JSON.stringify({
              type: "ice-candidate",
              sender: loggedInUser,
              receiver: msg.sender,
              candidate: event.candidate,
              callType: "video"   // 🔹 important so you know which PC to use
            }));
            console.log("[Receiver] Sent video ICE candidate to caller.");
          }
        };

        videoPc.ontrack = event => {
          console.log("[Receiver] Remote video track received:", event.streams);
          const remoteVideoEl = document.createElement("video");
          remoteVideoEl.srcObject = event.streams[0];
          remoteVideoEl.autoplay = true;
          remoteVideoEl.playsInline = true;
          addRemoteVideoTile(event.streams[0], msg.sender || "");
        };

      } else {
        // Keep your existing audio setup
        console.log("[Receiver] Setting up audio peer connection.");
        pc = createAudioPeerConnection();

        pc.onconnectionstatechange = () =>
          console.log("Audio connection state:", pc.connectionState);
        pc.oniceconnectionstatechange = () =>
          console.log("Audio ICE state:", pc.iceConnectionState);

        pc.onicecandidate = event => {
          if (event.candidate) {
            socket.send(JSON.stringify({
              type: "ice-candidate",
              sender: loggedInUser,
              receiver: msg.sender,
              candidate: event.candidate,
              callType: "audio"
            }));
          }
        };

        pc.ontrack = event => {
          if (event.track.kind === "video") {
            const videoEl = document.createElement("video");
            videoEl.srcObject = event.streams[0];
            videoEl.autoplay = true;
            videoEl.playsInline = true;
            addRemoteVideoTile(event.streams[0], msg.sender || "");
          } else {
            const audioEl = document.createElement("audio");
            audioEl.srcObject = event.streams[0];
            audioEl.autoplay = true;
            document.body.appendChild(audioEl);
          }
        };
      }

      // Save the offer SDP for later
      pendingOffer = msg.sdp;

      // Accept button for incoming call - this is where we set up the call after user clicks "Accept"
      document.getElementById("acceptCallBtn").onclick = async () => {
        try {
          document.getElementById("incomingCallInterface").style.display = "none";

          // Request only the media needed for the call type
          const stream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: msg.callType === "video"
          });

          if (msg.callType === "video") {
            document.getElementById("videoCallInterface").style.display = "block";

            const localVideoEl = document.getElementById("localVideoEl");
            if (localVideoEl) {
              localVideoEl.srcObject = stream;
              localVideoEl.autoplay = true;
              localVideoEl.playsInline = true;
            }

            stream.getTracks().forEach(track => videoPc.addTrack(track, stream));

            await videoPc.setRemoteDescription(new RTCSessionDescription(pendingOffer));

            for (const candidate of pendingCandidates) {
              try { await videoPc.addIceCandidate(new RTCIceCandidate(candidate)); } catch (_) {}
            }
            pendingCandidates = [];

            const answer = await videoPc.createAnswer();
            await videoPc.setLocalDescription(answer);
            socket.send(JSON.stringify({ type: "call-answer", callType: "video", sender: loggedInUser, receiver: msg.sender, sdp: answer }));

            document.getElementById("videoCallTitle").textContent = "Connected";
            if (document.getElementById("callUserName")) document.getElementById("callUserName").textContent = msg.sender;

            videoPc.ontrack = event => addRemoteVideoTile(event.streams[0], msg.sender || "");

            document.getElementById("videoHangupBtn").onclick = () => {
              stream.getTracks().forEach(t => t.stop());
              videoPc.close();
              clearVideoCall();
              document.getElementById("videoCallInterface").style.display = "none";
              document.getElementById("callOverlay").style.display = "none";
            };

          } else {
            document.getElementById("audioCallInterface").style.display = "block";

            // Only add audio tracks for audio call
            localStream = stream;
            stream.getAudioTracks().forEach(track => pc.addTrack(track, stream));

            await pc.setRemoteDescription(new RTCSessionDescription(pendingOffer));

            for (const candidate of pendingCandidates) {
              try { await pc.addIceCandidate(new RTCIceCandidate(candidate)); } catch (_) {}
            }
            pendingCandidates = [];

            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            socket.send(JSON.stringify({ type: "call-answer", callType: "audio", sender: loggedInUser, receiver: msg.sender, sdp: answer }));

            callStartTime = Date.now();
            durationInterval = setInterval(updateCallDuration, 1000);
            if (document.getElementById("callUserName")) document.getElementById("callUserName").textContent = msg.sender;
            document.getElementById("callStatus").textContent = "Connected";

            document.getElementById("hangupBtn").onclick = () => {
              clearInterval(durationInterval);
              stream.getTracks().forEach(t => t.stop());
              if (pc) { pc.close(); pc = null; }
              document.getElementById("audioCallInterface").style.display = "none";
              document.getElementById("callOverlay").style.display = "none";
            };
          }

        } catch (err) {
          console.error("[Accept] Failed to accept call:", err);
          // Restore incoming call UI so user can retry or dismiss
          document.getElementById("incomingCallInterface").style.display = "block";
          document.getElementById("callStatus") && (document.getElementById("callStatus").textContent = "Failed to connect");
          const errHint = document.getElementById("incomingCallPrompt");
          if (errHint) errHint.textContent = err.name === "NotAllowedError" ? "Microphone permission denied" : "Could not start call: " + err.message;
        }
        };

      // Decline button
      document.getElementById("declineCallBtn").onclick = () => {
        document.getElementById("callOverlay").style.display = "none";
        socket.send(JSON.stringify({
          type: "call-decline",
          sender: loggedInUser,
          receiver: msg.sender
        }));
      };
    }

    // Call end
    if (msg.type === "call-end" && msg.receiver === loggedInUser) {
      // Close peer connection
      if (pc) pc.close();
      if (videoPc) videoPc.close();

      // Clear timers
      clearInterval(durationInterval);
      clearInterval(videoDurationInterval);

      // Update UI
      document.getElementById("callStatus").textContent = "Call ended";
      document.getElementById("videoCallTitle").textContent = "Call Ended";
      document.getElementById("callOverlay").style.display = "none";
      clearVideoCall();
      if(document.getElementById("callUserName")) document.getElementById("callUserName").textContent = "";
    }

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

    let lastPreview = null;
    let lastMsgTime = null;

    for (const msg of history) {
      const who = msg.sender === loggedInUser ? "Me" : msg.sender;
      lastMsgTime = msg.timestamp;

      if (msg.msg_type === "text") {
        let plaintext;
        try {
          plaintext = await decryptMessage(msg.ciphertext, msg.nonce);
        } catch (err) {
          console.error("[DEBUG] Decryption failed:", err, msg);
          plaintext = "[Decryption failed]";
        }
        addMessageToUI(who, plaintext, msg.timestamp);
        lastPreview = plaintext.length > 40 ? plaintext.slice(0, 40) + "..." : plaintext;

      } else if (msg.msg_type === "file") {
        const imgExts = ["jpg", "jpeg", "png", "gif", "webp"];
        const ext = (msg.file_name || "").split(".").pop().toLowerCase();
        if (imgExts.includes(ext)) {
          addMessageToUI(who, makeMediaNode('img', '/uploads/' + msg.file_name), msg.timestamp);
          lastPreview = "Photo";
        } else {
          addMessageToUI(who, makeMediaNode('file', '/uploads/' + msg.file_name), msg.timestamp);
          lastPreview = "File";
        }

      } else if (msg.msg_type === "image") {
        addMessageToUI(who, makeMediaNode('img', '/uploads/' + msg.file_name), msg.timestamp);
        lastPreview = "Photo";

      } else if (msg.msg_type === "audio") {
        addMessageToUI(who, makeMediaNode('audio', '/uploads/' + msg.file_name), msg.timestamp);
        lastPreview = "Voice message";

      } else if (msg.msg_type === "call") {
        let callInfo = "";
        if (msg.status === "ended") {
          const secs = msg.duration || 0;
          const mm = String(Math.floor(secs / 60)).padStart(2, "0");
          const ss = String(secs % 60).padStart(2, "0");
          callInfo = "Call ended " + mm + ":" + ss;
          lastPreview = callInfo;
        } else if (msg.status === "missed") {
          callInfo = "Missed call from " + msg.sender;
          lastPreview = callInfo;
        } else if (msg.status === "declined") {
          callInfo = "Call declined";
          lastPreview = callInfo;
        }
        if (callInfo) addCallLogToUI(callInfo, msg.timestamp);
      }
    }

    // Update sidebar user-item preview
    const sidebarItem = document.querySelector('.user-item[data-user="' + user + '"]');
    if (sidebarItem) {
      const msgEl = sidebarItem.querySelector(".user-message");
      if (msgEl && lastPreview) msgEl.textContent = lastPreview;
      const timeEl = sidebarItem.querySelector(".message-time");
      if (timeEl && lastMsgTime) timeEl.textContent = formatTimestamp(lastMsgTime);
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
      activeReceiver = user;
      console.log("[DEBUG] activeReceiver set to:", activeReceiver);
      document.querySelectorAll('.user-item').forEach(el => el.classList.remove('active'));
      item.classList.add('active');
      generateAESKey(user).then(() => loadChatHistory(user)).catch(err => {
        console.error("[DEBUG] Failed to init AES key for", user, err);
        loadChatHistory(user);
      });
    } else {
      console.warn("[DEBUG] Clicked user-item without data-user attribute");
    }
  }
});

// Add message bubble to UI
function formatTimestamp(ts) {
  if (!ts) return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const d = new Date(ts);
  if (isNaN(d)) return ts;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function safeMediaUrl(url) {
  if (!url) return null;
  if (url.startsWith('/uploads/')) return url;
  try {
    const p = new URL(url, window.location.origin);
    if (p.protocol === 'https:' || p.protocol === 'http:') return url;
  } catch (_) {}
  return null;
}

function makeMediaNode(type, url, filename) {
  const safe = safeMediaUrl(url);
  if (type === 'img') {
    const img = document.createElement('img');
    img.src = safe || '';
    img.style.maxWidth = '200px';
    img.style.borderRadius = '8px';
    return img;
  }
  if (type === 'audio') {
    const aud = document.createElement('audio');
    aud.controls = true;
    aud.src = safe || '';
    return aud;
  }
  // file link
  const a = document.createElement('a');
  a.href = safe || '#';
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  a.textContent = filename || 'Download file';
  return a;
}

function addMessageToUI(sender, content, timestamp=null) {
  const chatBox = document.getElementById("chatMessages");
  const messageDiv = document.createElement("div");
  messageDiv.className = sender === "Me" ? "message sent" : "message received";

  const wrapper = document.createElement("div");
  wrapper.className = "message-wrapper";

  const contentDiv = document.createElement("div");
  contentDiv.className = "message-content";

  const textDiv = document.createElement("div");
  textDiv.className = "message-text";

  if (content instanceof Node) {
    textDiv.appendChild(content);
  } else {
    textDiv.textContent = String(content);
  }

  contentDiv.appendChild(textDiv);

  const tsDiv = document.createElement("div");
  tsDiv.className = "message-timestamp";
  tsDiv.textContent = formatTimestamp(timestamp);

  wrapper.appendChild(contentDiv);
  wrapper.appendChild(tsDiv);
  messageDiv.appendChild(wrapper);
  chatBox.appendChild(messageDiv);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function addCallLogToUI(callInfo, timestamp=null) {
  const chatBox = document.getElementById("chatMessages");
  const div = document.createElement("div");
  div.className = "message call-log";

  const content = document.createElement("div");
  content.className = "call-log-content";

  const text = document.createElement("span");
  text.className = "call-log-text";
  text.textContent = callInfo;

  const time = document.createElement("span");
  time.className = "call-log-time";
  time.textContent = formatTimestamp(timestamp);

  content.appendChild(text);
  content.appendChild(time);
  div.appendChild(content);
  chatBox.appendChild(div);
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
            previewFile(file);
            if (file.type.startsWith("image/")) {
                sendImage(file);
            } else {
                sendFile(file);
            }
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
        // 🔹 User list → Chat board toggle
    document.querySelectorAll('.user-list .user').forEach(user => {
        user.addEventListener('click', () => {
            document.querySelector('.user-list').style.display = 'none';
            document.querySelector('.chat-board').classList.add('active');
        });
    });

    // 🔹 Swipe gesture for mobile
    const chatBoard = document.querySelector('.chat-board');
    let touchStartX = 0;
    let touchEndX = 0;

    if (chatBoard) {
      chatBoard.addEventListener('touchstart', (e) => {
        touchStartX = e.changedTouches[0].screenX;
      });

      chatBoard.addEventListener('touchend', (e) => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
      });
    }

    function handleSwipe() {
      const swipeDistance = touchStartX - touchEndX;

      // Adjust threshold (e.g., 50px) to avoid accidental triggers
      if (swipeDistance > 50) {
        console.log("[DEBUG] Swipe left detected → back to user list");
        chatBoard.classList.remove('active');
        document.querySelector('.user-list').style.display = 'block';
      }
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

// Audio and video call controls handlers 
document.addEventListener("DOMContentLoaded", () => {
    // Audio call controls
    document.getElementById("muteBtn").addEventListener("click", () => {
        if (localStream) {
            const track = localStream.getAudioTracks()[0];
            track.enabled = !track.enabled;
        }
    });

    document.getElementById("hangupBtn").addEventListener("click", () => {
        if (pc) pc.close();
        document.getElementById("callStatus").textContent = "Call ended";
    });

    // Video mic toggle
    document.getElementById("videoMuteBtn").addEventListener("click", () => {
        if (localVideoStream) {
            const track = localVideoStream.getAudioTracks()[0];
            if (track) {
                track.enabled = !track.enabled;
                const icon = document.querySelector("#videoMuteBtn i");
                if (icon) icon.className = track.enabled ? "fas fa-microphone" : "fas fa-microphone-slash";
            }
        }
    });

    // Video camera toggle
    document.getElementById("videoCamBtn").addEventListener("click", () => {
        if (localVideoStream) {
            const track = localVideoStream.getVideoTracks()[0];
            if (track) {
                track.enabled = !track.enabled;
                const icon = document.querySelector("#videoCamBtn i");
                if (icon) icon.className = track.enabled ? "fas fa-video" : "fas fa-video-slash";
            }
        }
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

                const _fileNode = makeMediaNode('file', data.url, data.url.endsWith('.pdf') ? 'Open PDF' : 'Download file');
                addMessageToUI("Me", _fileNode, new Date().toISOString());
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
                addMessageToUI("Me", makeMediaNode('img', data.url), new Date().toISOString());

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
                addMessageToUI("Me", makeMediaNode('audio', data.url), new Date().toISOString());

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

function updateCallDuration() {
    const elapsed = Math.floor((Date.now() - callStartTime) / 1000);
    const minutes = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const seconds = String(elapsed % 60).padStart(2, "0");
    document.getElementById("callDuration").textContent = `${minutes}:${seconds}`;
}

function updateVideoCallDuration() {
    const elapsed = Math.floor((Date.now() - videoCallStartTime) / 1000);
    const h = String(Math.floor(elapsed / 3600)).padStart(2, "0");
    const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, "0");
    const s = String(elapsed % 60).padStart(2, "0");
    const meta = document.getElementById("videoCallMeta");
    if (meta) meta.textContent = `2 participants • ${h}:${m}:${s}`;
}

function addRemoteVideoTile(stream, name) {
    const grid = document.getElementById("remoteVideoGrid");
    if (!grid) return;
    if (grid.querySelector('[data-name="' + name + '"]')) return;
    const tile = document.createElement("div");
    tile.className = "participant";
    tile.dataset.name = name;
    const vid = document.createElement("video");
    vid.srcObject = stream;
    vid.autoplay = true;
    vid.playsInline = true;
    vid.play().catch(() => {});
    const label = document.createElement("div");
    label.className = "name";
    label.textContent = name;
    tile.appendChild(vid);
    tile.appendChild(label);
    grid.appendChild(tile);
}

function clearVideoCall() {
    const grid = document.getElementById("remoteVideoGrid");
    if (grid) grid.innerHTML = "";
    const localVid = document.getElementById("localVideoEl");
    if (localVid) localVid.srcObject = null;
}

// Audio Call
async function startAudioCall(receiver) {
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    pc = createAudioPeerConnection();

    // 🔍 Debug logs
    pc.onconnectionstatechange = () => {
        console.log("Connection state:", pc.connectionState);
    };
    pc.oniceconnectionstatechange = () => {
        console.log("ICE state:", pc.iceConnectionState);
    };

    // Add ICE candidate handler right after creating pc
    pc.onicecandidate = event => {
        if (event.candidate) {
            socket.send(JSON.stringify({
                type: "ice-candidate",
                callType: "audio",   // defined calltype
                sender: loggedInUser,
                receiver,
                candidate: event.candidate
            }));
        }
    };

    // Add local audio
    localStream.getTracks().forEach(track => pc.addTrack(track, localStream));

    // Handle remote audio
    pc.ontrack = event => {
        const audioEl = document.createElement("audio");
        audioEl.srcObject = event.streams[0];
        audioEl.autoplay = true;
        document.body.appendChild(audioEl);
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    socket.send(JSON.stringify({ 
      type:"call-offer", 
      callType:"audio", // for receiver to know which interface to show
      sender:loggedInUser, 
      receiver, 
      sdp:offer 
    }));

    // Update UI immediately for caller
    const callUserName = document.getElementById("callUserName");
    if (callUserName) callUserName.textContent = receiver;
    const callAvatar = document.getElementById("callAvatar");
    if (callAvatar) callAvatar.textContent = receiver[0].toUpperCase();
    document.getElementById("callStatus").textContent = "Calling...";
    document.getElementById("audioCallInterface").style.display = "flex";
    document.getElementById("videoCallInterface").style.display = "none";
    document.getElementById("callOverlay").style.display = "flex";

    // Listen for signaling
    // socket.addEventListener("message", async (event) => {
    //   const msg = JSON.parse(event.data);

    //   // Handle call answer for audio
    //   if (msg.type === "call-answer" && msg.receiver === loggedInUser && msg.callType === "audio") {
    //     await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
    //     callStartTime = Date.now();
    //     durationInterval = setInterval(updateCallDuration, 1000);
    //     document.getElementById("callStatus").textContent = "Connected";
    //   }

    //   // Handle ICE candidates for audio
    //   if (msg.type === "ice-candidate" && msg.receiver === loggedInUser && msg.callType === "audio") {
    //     try {
    //       await pc.addIceCandidate(new RTCIceCandidate(msg.candidate));
    //     } catch (err) {
    //       console.error("Error adding ICE candidate:", err);
    //     }
    //   }

    //   if (msg.type === "call-end" && msg.receiver === loggedInUser) {
    //     // Close peer connection
    //     if (pc) pc.close();

    //     // Clear timer
    //     clearInterval(durationInterval);

    //     // Update UI
    //     document.getElementById("callStatus").textContent = "Call ended";
    //     document.getElementById("callOverlay").style.display = "none";
    //     if(document.getElementById("callUserName")) document.getElementById("callUserName").textContent = "";
    //   }

    //   if (msg.type === "call-end" && msg.receiver === loggedInUser && msg.callType === "audio") {
    //     if (pc) pc.close();
    //     clearInterval(durationInterval);
    //     document.getElementById("callStatus").textContent = "Call ended";
    //     document.getElementById("callOverlay").style.display = "none";
    //     if(document.getElementById("callUserName")) document.getElementById("callUserName").textContent = "";
    //   }
    // });
}

// Audio call button
document.getElementById("audioCallBtn").addEventListener("click", () => {
    console.log("Audio call button clicked");
    startAudioCall(activeReceiver);
    document.getElementById("callOverlay").style.display = "flex"; // show overlay
});

document.getElementById("hangupBtn").onclick = () => {
    if (pc) { pc.close(); pc = null; }
    clearInterval(durationInterval);
    const elapsed = callStartTime ? Math.max(0, Math.floor((Date.now() - callStartTime) / 1000)) : 0;
    callStartTime = null;
    socket.send(JSON.stringify({
      type: "call-end",
      callType: "audio",
      sender: loggedInUser,
      receiver: activeReceiver,
      status: "ended",
      duration: elapsed
    }));
    if (elapsed > 0) {
      const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
      const ss = String(elapsed % 60).padStart(2, "0");
      addCallLogToUI(`📞 Call ended • ${mm}:${ss}`);
    }
    document.getElementById("audioCallInterface").style.display = "none";
    document.getElementById("callOverlay").style.display = "none";
};

// Video Call
async function startVideoCall(receiver) {
  localVideoStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });

  const localVid = document.getElementById("localVideoEl");
  if (localVid) localVid.srcObject = localVideoStream;
  const localLabel = document.getElementById("localVideoLabel");
  if (localLabel) localLabel.textContent = loggedInUser + " (You)";

  videoPc = createVideoPeerConnection();

  videoPc.onicecandidate = event => {
    if (event.candidate) {
      socket.send(JSON.stringify({
        type: "ice-candidate",
        callType: "video",
        sender: loggedInUser,
        receiver,
        candidate: event.candidate
      }));
    }
  };

  localVideoStream.getTracks().forEach(track => videoPc.addTrack(track, localVideoStream));

  videoPc.ontrack = event => {
    addRemoteVideoTile(event.streams[0], receiver);
  };

  const offer = await videoPc.createOffer();
  await videoPc.setLocalDescription(offer);

  socket.send(JSON.stringify({
    type: "call-offer",
    callType: "video",
    sender: loggedInUser,
    receiver,
    sdp: offer
  }));

  const title = document.getElementById("videoCallTitle");
  if (title) title.textContent = "Calling " + receiver + "...";
  document.getElementById("audioCallInterface").style.display = "none";
  document.getElementById("videoCallInterface").style.display = "block";
  document.getElementById("callOverlay").style.display = "flex";
}

// Audio signaling listener
socket.addEventListener("message", async (event) => {
  const msg = JSON.parse(event.data);
  if (msg.callType !== "audio") return;

  if (msg.type === "call-answer" && msg.receiver === loggedInUser) {
    try {
      await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
      for (const c of pendingAudioCandidates) {
        try { await pc.addIceCandidate(new RTCIceCandidate(c)); } catch (_) {}
      }
      pendingAudioCandidates = [];
      callStartTime = Date.now();
      durationInterval = setInterval(updateCallDuration, 1000);
      document.getElementById("callStatus").textContent = "Connected";
    } catch (err) { console.error("[Audio] setRemoteDescription failed:", err); }
  }

  if (msg.type === "ice-candidate" && msg.receiver === loggedInUser) {
    if (!pc || !pc.remoteDescription) {
      pendingAudioCandidates.push(msg.candidate);
    } else {
      try { await pc.addIceCandidate(new RTCIceCandidate(msg.candidate)); } catch (_) {}
    }
  }

  if (msg.type === "call-end" && msg.receiver === loggedInUser) {
    if (pc) pc.close();
    clearInterval(durationInterval);
    document.getElementById("callStatus").textContent = "Call ended";
    document.getElementById("callOverlay").style.display = "none";
  }
});

// Video signaling listener
socket.addEventListener("message", async (event) => {
  const msg = JSON.parse(event.data);
  if (msg.callType !== "video") return;

  if (msg.type === "call-answer" && msg.receiver === loggedInUser) {
    try {
      await videoPc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
      for (const c of pendingVideoCandidates) {
        try { await videoPc.addIceCandidate(new RTCIceCandidate(c)); } catch (_) {}
      }
      pendingVideoCandidates = [];
      videoCallStartTime = Date.now();
      videoDurationInterval = setInterval(updateVideoCallDuration, 1000);
      document.getElementById("videoCallTitle").textContent = "Connected";
    } catch (err) { console.error("[Video] setRemoteDescription failed:", err); }
  }

  if (msg.type === "ice-candidate" && msg.receiver === loggedInUser) {
    if (!videoPc || !videoPc.remoteDescription) {
      pendingVideoCandidates.push(msg.candidate);
    } else {
      try { await videoPc.addIceCandidate(new RTCIceCandidate(msg.candidate)); } catch (_) {}
    }
  }

  if (msg.type === "call-end" && msg.receiver === loggedInUser) {
    if (videoPc) videoPc.close();
    clearInterval(videoDurationInterval);
    document.getElementById("videoCallTitle").textContent = "Call Ended";
    clearVideoCall();
    document.getElementById("callOverlay").style.display = "none";
  }
});


// Hangup
document.getElementById("videoHangupBtn").onclick = () => {
  if (videoPc) videoPc.close();
  clearInterval(videoDurationInterval);

  if (localVideoStream) {
    localVideoStream.getTracks().forEach(track => track.stop());
  }

  const elapsed = videoCallStartTime ? Math.max(0, Math.floor((Date.now() - videoCallStartTime) / 1000)) : 0;
  videoCallStartTime = null;
  socket.send(JSON.stringify({
    type: "call-end",
    callType: "video",
    sender: loggedInUser,
    receiver: activeReceiver,
    status: "ended",
    duration: elapsed
  }));
  if (elapsed > 0) {
    const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const ss = String(elapsed % 60).padStart(2, "0");
    addCallLogToUI(`📹 Video call ended • ${mm}:${ss}`);
  }
  if (videoPc) { videoPc.close(); videoPc = null; }
  clearVideoCall();
  document.getElementById("videoCallInterface").style.display = "none";
  document.getElementById("callOverlay").style.display = "none";
};

//video call button
document.getElementById("videoCallBtn").addEventListener("click", () => {
    if (!activeReceiver) return;
    startVideoCall(activeReceiver);
});



// ---- Tab switching for sidebar nav icons ----
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".tab-swtich").forEach(el => {
    el.addEventListener("click", () => {
      const tab = el.dataset.tab;
      if (!tab) return;
      document.querySelectorAll(".nav-icon.tab-swtich, .mobile-nav-icon.tab-swtich").forEach(n => n.classList.remove("active"));
      el.classList.add("active");
      document.querySelectorAll(".tab-panel").forEach(p => { p.hidden = (p.id !== ("tab-" + tab)); });
    });
  });

  // Dropdown positioning and toggle
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".dropdown-btn");
    if (btn) {
      e.stopPropagation();
      const dropdown = btn.closest(".dropdown");
      const menu = dropdown && dropdown.querySelector(".dropdown-menu");
      if (!menu) return;
      const isOpen = menu.classList.contains("show");
      document.querySelectorAll(".dropdown-menu.show").forEach(m => m.classList.remove("show"));
      if (!isOpen) {
        const rect = btn.getBoundingClientRect();
        menu.style.top = (rect.bottom + 4) + "px";
        menu.style.left = (rect.left - menu.offsetWidth + rect.width) + "px";
        menu.classList.add("show");
      }
      return;
    }
    // Outside click closes all
    if (!e.target.closest(".dropdown-menu")) {
      document.querySelectorAll(".dropdown-menu.show").forEach(m => m.classList.remove("show"));
    }
  });
});