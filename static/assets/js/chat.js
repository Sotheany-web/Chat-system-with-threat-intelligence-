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

// Helper: create audio peer connection with STUN server
function createAudioPeerConnection() {
  return new RTCPeerConnection({
    iceServers: [
      { urls: "stun:stun.l.google.com:19302" }
      // Add TURN here for production if needed
      // { urls: "turn:your-turn-server.com", username: "user", credential: "pass" }
    ]
  });
}

// Helper: create video peer connection with STUN server
function createVideoPeerConnection() {
  return new RTCPeerConnection({
    iceServers: [
      { urls: "stun:stun.l.google.com:19302" }
    ]
  });
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

let pendingCandidates = [];

// decrypt message before displaying (receiver side)
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
      const who = msg.sender === loggedInUser ? "Me" : msg.sender;
      let plaintext;
      try {
        plaintext = await decryptMessage(msg.ciphertext, msg.nonce);
      } catch (err) {
        console.error("[DEBUG] Failed to decrypt text message:", err, msg);
        plaintext = "[Decryption failed]";
      }
      addMessageToUI(msg.sender === loggedInUser ? "Me" : msg.sender, plaintext, msg.timestamp);
      return;
    }

    if (msg.type === "call-offer" && msg.receiver === loggedInUser) {

      // 🔹 Show incoming call UI here
      document.getElementById("callOverlay").style.display = "block";
      document.getElementById("incomingCallInterface").style.display = "block";

      // 🔹 Hide other interfaces so receiver doesn't see caller UI
      document.getElementById("audioCallInterface").style.display = "none";   // CHANGE
      document.getElementById("videoCallInterface").style.display = "none";   // CHANGE

      // 🔹 Populate with caller info instead of defaults
      document.getElementById("incomingCallerName").innerText = msg.sender;   // CHANGE
      document.getElementById("incomingCallPrompt").innerText = `${msg.sender} is calling...`; // CHANGE

      // Create peer connection
      pc = createAudioPeerConnection();

      pc.onconnectionstatechange = () => console.log("Connection state:", pc.connectionState);
      pc.oniceconnectionstatechange = () => console.log("ICE state:", pc.iceConnectionState);

      // ICE candidate handler
      pc.onicecandidate = event => {
        if (event.candidate) {
            console.log("Sending ICE candidate:", event.candidate);
            socket.send(JSON.stringify({
                type: "ice-candidate",
                sender: loggedInUser,
                receiver: msg.sender,
                candidate: event.candidate
            }));
        }
      };

      // Handle remote tracks
      pc.ontrack = event => {
        const kind = event.track.kind;
        if (kind === "video") {
            const videoEl = document.createElement("video");
            videoEl.srcObject = event.streams[0];
            videoEl.autoplay = true;
            videoEl.playsInline = true;
            document.querySelector(".participants-grid").appendChild(videoEl);
        } else {
            const audioEl = document.createElement("audio");
            audioEl.srcObject = event.streams[0];
            audioEl.autoplay = true;
            document.body.appendChild(audioEl);
        }
    };

      // Save the offer SDP for later
      pendingOffer = msg.sdp;

      // Accept buttonc
      document.getElementById("acceptCallBtn").onclick = async () => {
        document.getElementById("incomingCallInterface").style.display = "none"; 

          // Add local mic/cam
          const stream = await navigator.mediaDevices.getUserMedia({ audio:true, video:true });

          // Check call type from the offer
          if (msg.callType === "video") {
            // Show video interface
            document.getElementById("videoCallInterface").style.display = "block";

            // Attach local preview
            const localVideoEl = document.querySelector("#videoCallInterface .main-video video");
            if (localVideoEl) {
              localVideoEl.srcObject = stream;
              localVideoEl.autoplay = true;
              localVideoEl.playsInline = true;
            }

            // Add local tracks
            stream.getTracks().forEach(track => videoPc.addTrack(track, stream));

            // Apply remote description
            await videoPc.setRemoteDescription(new RTCSessionDescription(pendingOffer));

            // Flush queued candidates
            for (const candidate of pendingCandidates) {
              try {
                await videoPc.addIceCandidate(new RTCIceCandidate(candidate));
              } catch (err) {
                console.error("Error adding queued ICE candidate:", err);
              }
            }
            pendingCandidates = [];

            // Create and send answer
            const answer = await videoPc.createAnswer();
            await videoPc.setLocalDescription(answer);
            socket.send(JSON.stringify({
              type: "call-answer",
              callType: "video",
              sender: loggedInUser,
              receiver: msg.sender,
              sdp: answer
            }));

            // 🔹 Update UI names/status
            document.querySelector(".call-user-name").innerText = msg.sender;
            document.querySelector("#videoCallInterface .call-header h2").textContent = "Connected";

            // Hangup cleanup
            document.getElementById("hangupBtn").onclick = () => {
              clearInterval(videoDurationInterval);
              document.getElementById("callOverlay").style.display = "none";
              stream.getTracks().forEach(track => track.stop()); // release mic/cam
              videoPc.close();
            };

          } else {
            // Show audio interface
            document.getElementById("audioCallInterface").style.display = "block";

            // Add local tracks
            stream.getTracks().forEach(track => pc.addTrack(track, stream));

            // Apply remote description
            await pc.setRemoteDescription(new RTCSessionDescription(pendingOffer));

            // Flush queued candidates
            for (const candidate of pendingCandidates) {
              try {
                await pc.addIceCandidate(new RTCIceCandidate(candidate));
              } catch (err) {
                console.error("Error adding queued ICE candidate:", err);
              }
            }
            pendingCandidates = [];

            // Create and send answer
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            socket.send(JSON.stringify({
              type: "call-answer",
              callType: "audio",
              sender: loggedInUser,
              receiver: msg.sender,
              sdp: answer
            }));

            // 🔹 Start call timer
            callStartTime = Date.now();
            durationInterval = setInterval(updateCallDuration, 1000);

            // 🔹 Update UI names/status
            document.querySelector(".call-user-name").innerText = msg.sender;
            document.getElementById("callStatus").innerText = "Connected";

            // Hangup cleanup
            document.getElementById("hangupBtn").onclick = () => {
              clearInterval(durationInterval);
              document.getElementById("callOverlay").style.display = "none";
              stream.getTracks().forEach(track => track.stop()); // release mic/cam
              pc.close();
            };
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

    // Call answer
    if (msg.type === "call-answer" && msg.receiver === loggedInUser) {
      console.log("Received call-answer from", msg.sender);
      await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));

      // Flush queued candidates
      for (const candidate of pendingCandidates) {
        try {
          await pc.addIceCandidate(new RTCIceCandidate(candidate));
        } catch (err) {
          console.error("Error adding queued ICE candidate:", err);
        }
      }
      pendingCandidates = [];
    }

    // ICE candidate
    if (msg.type === "ice-candidate" && msg.receiver === loggedInUser) {
      console.log("Received ICE candidate:", msg.candidate);
      if (pc && pc.remoteDescription && pc.remoteDescription.type) {
        try {
          await pc.addIceCandidate(new RTCIceCandidate(msg.candidate)); 
        } catch (err) {
          console.error("Error adding ICE candidate:", err);
        }
      } else {
        console.log("Queuing ICE candidate until remote description is set");
        pendingCandidates.push(msg.candidate);
      }
    }

    if (msg.type === "call-end" && msg.receiver === loggedInUser) {
      // Close peer connection
      if (pc) pc.close();
      if (videoPc) videoPc.close();

      // Clear timers
      clearInterval(durationInterval);
      clearInterval(videoDurationInterval);

      // Update UI
      document.getElementById("callStatus").textContent = "Call ended";
      document.querySelector("#videoCallInterface .call-header h2").textContent = "Call Ended";
      document.getElementById("callOverlay").style.display = "none";
      document.querySelector(".participants-grid").innerHTML = "";
      document.querySelector(".call-user-name").innerText = "";
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
      } else if (msg.msg_type === "call") {
        // Render call logs
        let callInfo = "";
        if (msg.status === "ended") {
          callInfo = `📞 Call ended • Duration: ${msg.duration}`;
        } else if (msg.status === "missed") {
          callInfo = `📞 Missed call`;
        } else if (msg.status === "declined") {
          callInfo = `📞 Call declined`;
        }

        // Show with timestamp
        addMessageToUI(who, callInfo, msg.timestamp);
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

    // Video call controls
    document.getElementById("videoHangupBtn").addEventListener("click", () => {
        if (pc) pc.close();
        document.querySelector(".call-header h2").textContent = "Video call ended";
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
    document.querySelector("#videoCallInterface .call-info p").textContent = `Duration • ${h}:${m}:${s}`;
}

// Audio Call
async function startAudioCall(receiver) {
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    pc = new RTCPeerConnection();

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
    socket.send(JSON.stringify({ type:"call-offer", sender:loggedInUser, receiver, sdp:offer }));

    document.querySelector(".call-user-name").innerText = receiver;
    document.getElementById("callStatus").textContent = "Calling...";
    document.getElementById("callOverlay").style.display = "block";

        // 🔹 Listen for answer *inside this function*
    socket.onmessage = async (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === "call-answer" && msg.receiver === loggedInUser) {
        await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));

        // Start timer only after answer
        callStartTime = Date.now();
        durationInterval = setInterval(updateCallDuration, 1000);
        document.getElementById("callStatus").textContent = "Connected";
      }

      if (msg.type === "call-end" && msg.receiver === loggedInUser) {
        // Close peer connection
        if (pc) pc.close();

        // Clear timer
        clearInterval(durationInterval);

        // Update UI
        document.getElementById("callStatus").textContent = "Call ended";
        document.getElementById("callOverlay").style.display = "none";
        document.querySelector(".call-user-name").innerText = "";
      }

      if (msg.type === "ice-candidate" && msg.receiver === loggedInUser) {
        try {
          await pc.addIceCandidate(new RTCIceCandidate(msg.candidate));
        } catch (err) {
          console.error("Error adding ICE candidate:", err);
        }
      }
    };
}

// Audio call button
document.getElementById("audioCallBtn").addEventListener("click", () => {
    console.log("Audio call button clicked");
    startAudioCall(activeReceiver);
    document.getElementById("callOverlay").style.display = "block"; // show overlay
});

document.getElementById("hangupBtn").onclick = () => {
    if (pc) pc.close();
    clearInterval(durationInterval);
    const elapsed = Math.floor((Date.now() - callStartTime) / 1000);
    socket.send(JSON.stringify({ type:"call-end", receiver:activeReceiver, status:"ended", duration:elapsed }));
    document.getElementById("callStatus").textContent = "Call ended";
    document.getElementById("callOverlay").style.display = "none"; // hide overlay
};

// Video Call
async function startVideoCall(receiver) {
    localVideoStream = await navigator.mediaDevices.getUserMedia({ audio:true, video:true });
    document.querySelector("#videoCallInterface .main-video video").srcObject = localVideoStream;

    videoPc = createVideoPeerConnection();

    // 🔑 Add ICE candidate handler
    videoPc.onicecandidate = event => {
        if (event.candidate) {
            socket.send(JSON.stringify({
                type: "ice-candidate",
                sender: loggedInUser,
                receiver,
                candidate: event.candidate
            }));
        }
    };

    // Add local tracks
    localVideoStream.getTracks().forEach(track => videoPc.addTrack(track, localVideoStream));

    // Handle remote tracks    
    videoPc.ontrack = event => {
        const remoteVideoEl = document.createElement("video");
        remoteVideoEl.srcObject = event.streams[0];
        remoteVideoEl.autoplay = true;
        remoteVideoEl.playsInline = true;
        document.querySelector(".participants-grid").appendChild(remoteVideoEl);
    };

    // Create offer
    const offer = await videoPc.createOffer();
    await videoPc.setLocalDescription(offer);
    
    // Send offer via WebSocket
    socket.send(JSON.stringify({
      type:"call-offer",
      callType:"video",   // 🔹 important
      sender:loggedInUser,
      receiver,
      sdp:offer
    }));

    // Update UI
    document.querySelector("#videoCallInterface .call-header h2").textContent = `Calling ${receiver}...`;
    document.getElementById("callOverlay").style.display = "block";

    // Listen for answer and ICE candidates
    socket.addEventListener("message", async (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === "call-answer" && msg.receiver === loggedInUser) {
        await videoPc.setRemoteDescription(new RTCSessionDescription(msg.sdp));

        // Start timer only after answer
        videoCallStartTime = Date.now();
        videoDurationInterval = setInterval(updateVideoCallDuration, 1000);
        document.querySelector("#videoCallInterface .call-header h2").textContent = "Connected";
      }

      if (msg.type === "ice-candidate" && msg.receiver === loggedInUser) {
        try {
          await videoPc.addIceCandidate(new RTCIceCandidate(msg.candidate));
        } catch (err) {
          console.error("Error adding ICE candidate:", err);
        }
      }

      // 🔹 Handle call-end from the other side
      if (msg.type === "call-end" && msg.receiver === loggedInUser) {
        if (videoPc) videoPc.close();
        clearInterval(videoDurationInterval);

        document.querySelector("#videoCallInterface .call-header h2").textContent = "Call Ended";
        document.querySelector(".participants-grid").innerHTML = ""; // clear tiles
        document.getElementById("callOverlay").style.display = "none";
      }
    });
}

// Hangup
document.getElementById("videoHangupBtn").onclick = () => {
  if (videoPc) videoPc.close();
  clearInterval(videoDurationInterval);

  if (localVideoStream) {
    localVideoStream.getTracks().forEach(track => track.stop());
  }

  const elapsed = Math.floor((Date.now() - videoCallStartTime) / 1000);
  socket.send(JSON.stringify({ 
    type:"call-end", 
    receiver:activeReceiver, 
    status:"ended", 
    duration:elapsed 
  }));

  document.querySelector("#videoCallInterface .call-header h2").textContent = "Call Ended";
  document.querySelector(".participants-grid").innerHTML = "";
  document.querySelector("#videoCallInterface .main-video video").srcObject = null;
  document.getElementById("callOverlay").style.display = "none";
};

//video call button
document.getElementById("videoCallBtn").addEventListener("click", () => {
    console.log("Video call button clicked");
    startVideoCall(activeReceiver);

    // 🔹 Show overlay and caller name
    document.querySelector(".call-user-name").innerText = activeReceiver;
    document.querySelector("#videoCallInterface .call-header h2").textContent = `Calling ${activeReceiver}...`;
    document.getElementById("callOverlay").style.display = "block"; // show overlay
});


