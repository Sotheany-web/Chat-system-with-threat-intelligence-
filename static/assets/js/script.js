/* 
Name                 : MsgNest – Free Modern Chat UI Template built with HTML, CSS & Bootstrap
Author               : TemplateRise
Url                  : https://www.templaterise.com/template/msgnest-free-modern-chat-ui-template-built-with-html-css-bootstrap
*/


document.addEventListener('DOMContentLoaded', () => {
  /* ── helper ─────────────────────────────── */
  const $ = id => document.getElementById(id);

  /* ── DOM refs ───────────────────────────── */
  const el = {
    /* layout */
    sidebar:           $('sidebar'),
    chatMain:          $('chatMain'),
    overlay:           $('overlay'),
    mobileMenuBtn:     $('mobileMenuBtn'),
    mobileBackBtn:     $('mobileBackBtn'),

    /* right panes */
    chatUserInfo:      $('chatUserInfo'),
    rightSidebar:      $('rightSidebar'),
    rightSearchSidebar:$('searchSidebar'),
    closeRightSidebar: $('closeRightSidebar'),
    closeSearchSidebar:$('closeSearchSidebar'),
    moreOptionsBtn:    $('moreOptionsBtn'),
    SearchBtn:         $('SearchBtn'),

    /* theme */
    themeToggle:       $('themeToggle'),
    themeToggleVideo:  $('themeToggleVideo'),

    /* messaging */
    messageInput:      $('messageInput'),
    sendButton:        $('sendButton'),
    chatMessages:      $('chatMessages'),

    /* file attach */
    attachFileBtn:     $('attachFileBtn'),
    sendImageBtn:      $('sendImageBtn'),
    fileInput:         $('fileInput'),
    imageInput:        $('imageInput'),
    filePreview:       $('filePreview'),

    /* call UI */
    callOverlay:       $('callOverlay'),
    audioCallInterface:$('audioCallInterface'),
    videoCallInterface:$('videoCallInterface'),
    callStatus:        $('callStatus'),
    videoCallStatus:   $('videoCallStatus'),
    callDuration:      $('callDuration'),
    videoDuration:     $('videoDuration'),
    muteBtn:           $('muteBtn'),
    speakerBtn:        $('speakerBtn'),
    hangupBtn:         $('hangupBtn'),
    videoMuteBtn:      $('videoMuteBtn'),
    videoCameraBtn:    $('videoCameraBtn'),
    videoHangupBtn:    $('videoHangupBtn'),
    audioCallBtn:      $('audioCallBtn'),
    videoCallBtn:      $('videoCallBtn'),
    profileAudioBtn:   $('profileAudioBtn'),
    profileVideoBtn:   $('profileVideoBtn'),

    /* chat‑header (mobile) */
    currentChatName:   document.querySelectorAll('.currentChatName'), 
    currentChatAvatar: document.querySelectorAll('.currentChatAvatar'),

    typing_indicator: document.querySelector('.typing-indicator'),

    /* mobile nav */
    mobileBottomNav:   $('mobileBottomNav'),

    navIcons: document.querySelectorAll('.tab-swtich[data-tab]'),
    panels: document.querySelectorAll('.tab-panel'),
  };


  /* ── state ──────────────────────────────── */
  let isRightSidebarOpen   = false;
  let isSearchSidebarOpen  = false;
  let isMuted              = false;
  let isSpeakerOn          = false;
  let isCameraOn           = true;
  let callTimer            = null;
  let callStartTime        = null;
  let pendingFiles         = [];
  let activeDropdown       = null;
  let isMobile             = window.innerWidth <= 1024;
  let activeChat = false;
  let keyboardVisible = false;


  // function updateBottomNavVisibility() {
  //       if (isMobile && el.mobileBottomNav) {
  //           if (activeChat || keyboardVisible) {
  //               el.mobileBottomNav.style.display = 'none';
  //           } else {
  //               el.mobileBottomNav.style.display = 'flex';
  //           }
  //       }
  // }

  function updateBottomNavVisibility() {
  if (el.mobileBottomNav) {
    if (window.innerWidth > 1024) {
      el.mobileBottomNav.style.display = 'none';
    } else {
      if (activeChat || keyboardVisible) {
        el.mobileBottomNav.style.display = 'none';
      } else {
        el.mobileBottomNav.style.display = 'flex';
      }
    }
  }
}


  updateBottomNavVisibility();

  
 /* ── bottom‑nav helpers (core CSS) ──────── */
  const hideBottomNav = () => {
    if(activeChat){
    if (el.mobileBottomNav) el.mobileBottomNav.style.display = 'none';
    }
  };
  const showBottomNav = () => {
     if(!activeChat){
       if (isMobile && el.mobileBottomNav) el.mobileBottomNav.style.display = 'flex';
     }  
  };


  if (isMobile) showBottomNav(); else hideBottomNav();


  const currentTheme = localStorage.getItem('theme') || 'light';
  document.body.dataset.theme = currentTheme;
  updateThemeIcon(currentTheme);

  [el.themeToggle, el.themeToggleVideo].forEach(btn => {
    btn?.addEventListener('click', toggleTheme);
  });

  function toggleTheme() {
    const newTheme = document.body.dataset.theme === 'light' ? 'dark' : 'light';
    document.body.dataset.theme = newTheme;
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
  }

  function updateThemeIcon(theme) {
    const icon = theme === 'dark'
      ? '<i class="fas fa-moon"></i>'
      : '<i class="fas fa-sun"></i>';
    if (el.themeToggle) el.themeToggle.innerHTML = icon;
    if (el.themeToggleVideo) el.themeToggleVideo.innerHTML = icon;
  }

  /* ── sidebars / overlay ─────────────────── */
  el.mobileMenuBtn?.addEventListener('click', toggleSidebar);
  el.overlay?.addEventListener('click', toggleSidebar);
  el.chatUserInfo?.addEventListener('click', toggleRightSidebar);
  el.moreOptionsBtn?.addEventListener('click', toggleRightSidebar);
  el.closeRightSidebar?.addEventListener('click', toggleRightSidebar);
  el.SearchBtn?.addEventListener('click', toggleSearchSidebar);
  el.closeSearchSidebar?.addEventListener('click', toggleSearchSidebar);

  function toggleSidebar () {
    el.sidebar?.classList.toggle('open');
    el.overlay?.classList.toggle('show');
  }
  function toggleRightSidebar () {
    if (!isRightSidebarOpen) closeSearchSidebar();
    isRightSidebarOpen = !isRightSidebarOpen;
    el.rightSidebar?.classList.toggle('open', isRightSidebarOpen);
    updateMainShift();
  }
  function toggleSearchSidebar () {
    if (!isSearchSidebarOpen) closeRightSidebar();
    isSearchSidebarOpen = !isSearchSidebarOpen;
    el.rightSearchSidebar?.classList.toggle('open', isSearchSidebarOpen);
    updateMainShift();
  }
  function closeRightSidebar () {
    if (isRightSidebarOpen) { isRightSidebarOpen = false; el.rightSidebar?.classList.remove('open'); }
  }
  function closeSearchSidebar () {
    if (isSearchSidebarOpen) { isSearchSidebarOpen = false; el.rightSearchSidebar?.classList.remove('open'); }
  }
  function updateMainShift () {
    el.chatMain?.classList.toggle('shifted', isRightSidebarOpen || isSearchSidebarOpen);
  }


el.navIcons.forEach(icon => {
    icon.addEventListener('click', () => {
        const target = icon.dataset.tab;
        el.navIcons.forEach(i => i.classList.toggle('active', i === icon));

        el.panels.forEach(p => {
            p.hidden = p.id !== `tab-${target}`;
        });
    });
});

  /* ── mobile nav / user list ─────────────── */
  if (isMobile) setupMobileNavigation();

  window.addEventListener('resize', () => {
    isMobile = window.innerWidth <= 1024;
    updateBottomNavVisibility();
  });


  if ('visualViewport' in window) {
      const visualViewport = window.visualViewport;
      
      visualViewport.addEventListener('resize', function() {
          // Check if keyboard is open
          keyboardVisible = (window.innerHeight - visualViewport.height) > 100;
          updateBottomNavVisibility();
          
          if (keyboardVisible && el.chatMessages) {
              // Scroll to bottom when keyboard appears
              el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
          }
      });
  }

  el.mobileBackBtn?.addEventListener('click', () => {
    activeChat = false;
    updateBottomNavVisibility();
    el.chatMain?.classList.remove('active');
    el.sidebar?.style.setProperty('display', 'flex');
  });

  function setupMobileNavigation () {
    document.querySelectorAll('.mobile-nav-icon').forEach(icon => {
      icon.addEventListener('click', () => {
        document.querySelectorAll('.mobile-nav-icon').forEach(i => i.classList.remove('active'));
        icon.classList.add('active');
      });
    });
  }

 

function setupUserSelection () {
    document.querySelectorAll('.user-item').forEach(item => {
      item.addEventListener('click', () => {
        const name   = item.querySelector('.user-name')?.textContent  || '';
        const avatar = item.querySelector('.user-avatar')?.textContent || '';

        el.currentChatName.forEach(n => n.textContent   = name);
        el.currentChatAvatar.forEach(a => a.textContent = avatar);

       activeChat = true;
       updateBottomNavVisibility();

        if (isMobile) {
          el.mobileBottomNav.style.display = 'none';
          el.sidebar?.style.setProperty('display', 'none');
          el.chatMain?.classList.add('active');
        }
      });
    });
  }

   setupUserSelection();

  /* ── messaging ──────────────────────────── */
  el.sendButton?.addEventListener('click', sendMessage);
  el.messageInput?.addEventListener('keypress', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  function sendMessage () {
    const text = el.messageInput?.value.trim();
    if (text) { addMessage(text, 'sent'); el.messageInput.value = ''; }
  
    if (pendingFiles.length) {
      pendingFiles.forEach(f => {
        const kind = f.type.split('/')[0];
        if      (kind === 'image') addImageMessage(f);
        else if (kind === 'video') addVideoMessage(f);
        else                       addFileMessage(f);
      });
      pendingFiles = [];
      renderFilePreview();
    }
    if (text || pendingFiles.length) scrollToBottom();

    el.typing_indicator.style.setProperty('display', 'none');
  }

  function addMessage (text, type) {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const div  = document.createElement('div');
    div.className = `message ${type}`;
    div.dataset.messageId = Date.now();
    div.innerHTML = `
      <div class="message-wrapper">
        <div class="message-content"><div class="message-text">${text}</div></div>
        <div class="message-timestamp">
          ${time}
          ${type === 'sent' ? '<div class="message-status single-tick"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 30" class="single-tick" width="16px" height="16px"><path d="M 26.980469 5.9902344 A 1.0001 1.0001 0 0 0 26.292969 6.2929688 L 11 21.585938 L 4.7070312 15.292969 A 1.0001 1.0001 0 1 0 3.2929688 16.707031 L 10.292969 23.707031 A 1.0001 1.0001 0 0 0 11.707031 23.707031 L 27.707031 7.7070312 A 1.0001 1.0001 0 0 0 26.980469 5.9902344 z"></path></svg></div>' : ''}
        </div>
        ${type === 'sent' ? dropdownTpl() : ''}
      </div>`;
    el.chatMessages?.appendChild(div);
  }

  const dropdownTpl = () => `
    <div class="message-actions">
      <button class="message-action-btn more-options" title="More options"><i class="fas fa-ellipsis-v"></i></button>
      <div class="message-dropdown">
        <div class="dropdown-item edit"><i class="fas fa-pencil-alt"></i> Edit</div>
        <div class="dropdown-item delete"><i class="fas fa-trash"></i> Delete</div>
      </div>
    </div>`;

  const scrollToBottom = () => {
    if (el.chatMessages) el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
  };

  /* file inputs */
  el.attachFileBtn?.addEventListener('click', () => el.fileInput?.click());
  el.sendImageBtn?.addEventListener('click',  () => el.imageInput?.click());
  el.fileInput?.addEventListener('change',  fileSelectHandler);
  el.imageInput?.addEventListener('change', fileSelectHandler);

  function fileSelectHandler (e) {
    pendingFiles.push(...Array.from(e.target.files));
    renderFilePreview();
    e.target.value = '';
  }

  el.filePreview?.addEventListener('click', e => {
    if (e.target.classList.contains('file-preview-remove')) {
      pendingFiles.splice(+e.target.dataset.index, 1);
      renderFilePreview();
    }
  });

  function renderFilePreview () {
    const preview = el.filePreview;
    if (!preview) return;
    preview.innerHTML = '';
    pendingFiles.forEach((f, i) => {
      const img = f.type.startsWith('image');
      preview.insertAdjacentHTML('beforeend', `
        <div class="file-preview-item">
          <div class="file-preview-icon ${img ? 'image' : 'document'}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              ${img
                ? '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21,15 16,10 5,21"></polyline>'
                : '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14,2 14,8 20,8"></polyline>'}
            </svg>
          </div>
          <div class="file-preview-info">
            <div class="file-preview-name">${f.name}</div>
            <div class="file-preview-size">${fmtSize(f.size)}</div>
          </div>
          <button class="file-preview-remove" data-index="${i}">×</button>
        </div>`);
    });
    preview.classList.toggle('show', pendingFiles.length > 0);
  }

  const fmtSize = b => {
    if (!b) return '0 Bytes';
    const k = 1024, sizes = ['Bytes','KB','MB','GB','TB'];
    const i = Math.floor(Math.log(b) / Math.log(k));
    return `${(b / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  };

  /* media‑message helpers */
  const addImageMessage = f => readerTpl(f, src => `<img src="${src}" alt="">`);
  const addVideoMessage = f => readerTpl(f, src => `<video controls><source src="${src}" type="${f.type}"></video>`);

  function readerTpl (file, makeInner) {
    const reader = new FileReader();
    reader.onload = e => {
      const t = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      el.chatMessages?.insertAdjacentHTML('beforeend', `
        <div class="message sent">
          <div class="message-wrapper">
            <div class="message-content">${makeInner(e.target.result)}</div>
            <div class="message-timestamp">${t}</div>${dropdownTpl()}
          </div>
        </div>`);
      scrollToBottom();
    };
    reader.readAsDataURL(file);
  }

  function addFileMessage (file) {
    const t = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    el.chatMessages?.insertAdjacentHTML('beforeend', `
      <div class="message sent">
        <div class="message-wrapper">
          <div class="message-content">
            <div class="file-message">
              <div class="file-icon document"><i class="fas fa-file"></i></div>
              <div class="file-info">
                <div class="file-name">${file.name}</div>
                <div class="file-size">${fmtSize(file.size)}</div>
              </div>
              <button class="file-download"><i class="fas fa-download"></i></button>
            </div>
          </div>
          <div class="message-timestamp">${t}</div>${dropdownTpl()}
        </div>
      </div>`);
    scrollToBottom();
  }

  /* dropdown positioning */
  document.addEventListener('click', e => {
    if (activeDropdown && !e.target.closest('.message-actions')) {
      hideDropdown(activeDropdown);
      activeDropdown = null;
    }

    const btn = e.target.closest('.message-action-btn.more-options');
    if (btn) {
      const wrap = btn.closest('.message-actions');
      const dd   = wrap.querySelector('.message-dropdown');

      if (activeDropdown && activeDropdown !== dd) hideDropdown(activeDropdown);

      dd.classList.toggle('show');
      activeDropdown = dd.classList.contains('show') ? dd : null;

      if (activeDropdown) positionDropdown(dd, wrap);
      e.stopPropagation();
    }
  });

  const hideDropdown = d => { d.classList.remove('show','open-left','open-up'); d.style.transform=''; };

  function positionDropdown (d, wrap) {
    d.classList.remove('open-left','open-up');
    d.style.transform = '';

    if (wrap.closest('.message.received')) d.classList.add('open-left');

    const vpW = innerWidth, vpH = innerHeight;
    const rect = d.getBoundingClientRect();
    if (rect.right  > vpW) d.classList.add('open-left');
    if (rect.left   <   0) d.classList.remove('open-left');
    if (rect.bottom > vpH) d.classList.add('open-up');

    const r2 = d.getBoundingClientRect();
    let dx = 0, dy = 0;
    if (r2.right  > vpW) dx = vpW - r2.right - 8;
    if (r2.left   < 0 )  dx = -r2.left + 8;
    if (r2.bottom > vpH) dy = vpH - r2.bottom - 8;
    if (r2.top    < 0 )  dy = -r2.top + 8;
    if (dx || dy) d.style.transform = `translate(${dx}px,${dy}px)`;
  }

  /* calls (audio / video) */
  el.audioCallBtn?.addEventListener('click', () => startCall('audio'));
  el.videoCallBtn?.addEventListener('click', () => startCall('video'));
  el.profileAudioBtn?.addEventListener('click', () => startCall('audio'));
  el.profileVideoBtn?.addEventListener('click', () => startCall('video'));
  el.hangupBtn?.addEventListener('click', endCall);
  el.videoHangupBtn?.addEventListener('click', endCall);
  el.muteBtn?.addEventListener('click', toggleMute);
  el.videoMuteBtn?.addEventListener('click', toggleMute);
  el.speakerBtn?.addEventListener('click', toggleSpeaker);
  el.videoCameraBtn?.addEventListener('click', toggleCamera);

  function startCall (type) {
    el.callOverlay?.classList.add('show');

    if (el.audioCallInterface) el.audioCallInterface.style.display = type === 'audio' ? 'block' : 'none';
    if (el.videoCallInterface) el.videoCallInterface.style.display = type === 'video' ? 'block' : 'none';

    if (el.callStatus)      el.callStatus.textContent      = 'Ringing...';
    if (el.videoCallStatus) el.videoCallStatus.textContent = 'Ringing...';

    setTimeout(() => {
      if (el.callStatus)      el.callStatus.textContent      = 'Connected';
      if (el.videoCallStatus) el.videoCallStatus.textContent = 'Connected';
      startCallTimer();
    }, 2000);
  }

  function endCall () {
    el.callOverlay?.classList.remove('show');
    clearInterval(callTimer); callTimer = null; callStartTime = null;

    if (el.callDuration)   el.callDuration.textContent   = '00:00';
    if (el.videoDuration)  el.videoDuration.textContent  = '00:00';
  }

  function toggleMute ()    { isMuted     = !isMuted;  el.muteBtn?.classList.toggle('active', isMuted); el.videoMuteBtn?.classList.toggle('active', isMuted); }
  function toggleSpeaker () { isSpeakerOn = !isSpeakerOn; el.speakerBtn?.classList.toggle('active', isSpeakerOn); }
  function toggleCamera ()  { isCameraOn  = !isCameraOn;  el.videoCameraBtn?.classList.toggle('active', !isCameraOn); }

  function startCallTimer () {
    callStartTime = new Date();
    callTimer = setInterval(() => {
      const diff = Math.floor((Date.now() - callStartTime) / 1000);
      const m = String(Math.floor(diff / 60)).padStart(2,'0');
      const s = String(diff % 60).padStart(2,'0');
      const t = `${m}:${s}`;

      if (el.callDuration)  el.callDuration.textContent  = t;
      if (el.videoDuration) el.videoDuration.textContent = t;
    }, 1000);
  }

  if ('visualViewport' in window) {
    const viewport = window.visualViewport;
    viewport.addEventListener('resize', () => {
      keyboardVisible = (window.innerHeight - viewport.height) > 100;
      updateBottomNavVisibility();
      document.body.classList.toggle('keyboard-visible', keyboardVisible);
      if (keyboardVisible && el.chatMessages) {
        el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
      }
    });
  } else {
    window.addEventListener('resize', () => {
      const h = window.innerHeight;
      const last = +document.body.dataset.lastHeight || h;
      if (Math.abs(h - last) > 200) {
        keyboardVisible = h < last;
        document.body.dataset.lastHeight = h;
        updateBottomNavVisibility();
        document.body.classList.toggle('keyboard-visible', keyboardVisible);
      }
    });
  }

  if (el.messageInput) {
    el.messageInput.addEventListener('focus', function() {
      // Set keyboard visible state
      keyboardVisible = true;
      updateBottomNavVisibility();
    });
    
    el.messageInput.addEventListener('blur', function() {
      // Set keyboard hidden state
      keyboardVisible = false;
      updateBottomNavVisibility();
    });
  }

    document.querySelectorAll('.filter-tab').forEach(tab => {
        tab.addEventListener('click', function() {
            document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');
        });
    });

    const backgroundInput = document.getElementById('backgroundInput');
    const profileInput = document.getElementById('profileInput');
    const backgroundOverlay = document.getElementById('backgroundOverlay');
    const profileImage = document.getElementById('profileImage');

    const backgroundBtn = backgroundOverlay.querySelector('.edit-btn');
    const profileBtn = document.querySelector('.camera-btn');

    backgroundBtn.addEventListener('click', () => backgroundInput.click());
    profileBtn.addEventListener('click', () => profileInput.click());

    backgroundInput.addEventListener('change', (event) => {
      const file = event.target.files[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = (e) => {
        backgroundOverlay.style.backgroundImage = `url(${e.target.result})`;
      };
      reader.readAsDataURL(file);
    });

    profileInput.addEventListener('change', (event) => {
      const file = event.target.files[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = (e) => {
        profileImage.src = e.target.result;
      };
      reader.readAsDataURL(file);
    });


    new SmartDropdown({
        selector: '.dropdown-btn',
        gap: 6,
        edge: 8,
        defaultDir: 'top right'
    });

    new Accordion({
        selector: '.settings-section',
        oneAtATime: true, 
        duration: 250 
    });
    
    new ImageLightbox();

});

