from flask import Flask, request, jsonify, send_file, render_template_string, send_from_directory
from flask_cors import CORS
import yt_dlp
import os
import uuid
import requests
import threading
import time
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# Configuration
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Store download status and cleanup old files
download_status = {}
file_cleanup_interval = 3600  # 1 hour

def cleanup_old_files():
    """Remove files older than 1 hour"""
    while True:
        try:
            current_time = datetime.now()
            for filename in os.listdir(DOWNLOAD_DIR):
                file_path = os.path.join(DOWNLOAD_DIR, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                    if current_time - file_time > timedelta(hours=1):
                        os.remove(file_path)
                        print(f"Cleaned up old file: {filename}")
        except Exception as e:
            print(f"Cleanup error: {e}")
        
        time.sleep(file_cleanup_interval)

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

def download_soundcloud_track_async(url, track_id):
    """Download SoundCloud track using yt-dlp in background"""
    try:
        print(f"Starting async download for track_id: {track_id}")
        download_status[track_id] = {'status': 'downloading', 'progress': 0}
        
        t0 = time.time()
        audio_out = os.path.join(DOWNLOAD_DIR, f"{track_id}.%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio',
            'outtmpl': audio_out,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'quiet': True,
            'noplaylist': True
        }
        
        download_status[track_id]['progress'] = 25
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        
        download_status[track_id]['progress'] = 60
        t1 = time.time()
        print(f"Audio download/conversion took {t1 - t0:.2f} seconds")
        
        # Get track info
        title = info.get('title', 'Unknown Track')
        thumbnail_url = info.get('thumbnail')
        
        # Download cover image if available
        cover_path = None
        cover_ext = None
        if thumbnail_url:
            try:
                img_ext = thumbnail_url.split('.')[-1].split('?')[0]
                if img_ext.lower() in ['jpg', 'jpeg', 'png', 'webp']:
                    cover_ext = img_ext
                else:
                    cover_ext = 'jpg'
                
                cover_path = os.path.join(DOWNLOAD_DIR, f"{track_id}_cover.{cover_ext}")
                response = requests.get(thumbnail_url, timeout=10)
                response.raise_for_status()
                
                with open(cover_path, 'wb') as f:
                    f.write(response.content)
                    
                download_status[track_id]['progress'] = 85
            except Exception as e:
                print(f"Error downloading cover: {e}")
                cover_path = None
                cover_ext = None
        
        mp3_path = os.path.join(DOWNLOAD_DIR, f"{track_id}.mp3")
        
        download_status[track_id] = {
            'status': 'completed',
            'progress': 100,
            'title': title,
            'mp3_path': mp3_path,
            'cover_path': cover_path,
            'cover_ext': cover_ext,
            'thumbnail_url': thumbnail_url,
            'mp3_available': os.path.exists(mp3_path),
            'cover_available': cover_path and os.path.exists(cover_path)
        }
        
        t2 = time.time()
        print(f"Total async download took {t2 - t0:.2f} seconds for track_id: {track_id}")
        
    except Exception as e:
        print(f"Async download error for track_id {track_id}: {e}")
        download_status[track_id] = {
            'status': 'error',
            'progress': 0,
            'error': str(e)
        }

def fetch_soundcloud_metadata(url):
    """Fetch SoundCloud track metadata using yt-dlp (no download)"""
    try:
        ydl_opts = {
            'quiet': True,
            'noplaylist': True,
            'skip_download': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        title = info.get('title', 'Unknown Track')
        thumbnail_url = info.get('thumbnail')
        # Try to get cover extension
        cover_ext = None
        if thumbnail_url:
            img_ext = thumbnail_url.split('.')[-1].split('?')[0]
            if img_ext.lower() in ['jpg', 'jpeg', 'png', 'webp']:
                cover_ext = img_ext
            else:
                cover_ext = 'jpg'
        return {
            'success': True,
            'title': title,
            'thumbnail_url': thumbnail_url,
            'cover_ext': cover_ext
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

@app.route('/')
def index():
    """Serve the frontend HTML"""
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SoundCloud MP3 Downloader</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #ff3c00;
            --primary-light: #ffb199;
            --bg: #f6f8fa;
            --container-bg: #fff;
            --shadow: 0 8px 32px rgba(0,0,0,0.10);
            --radius: 18px;
            --input-bg: #f2f3f7;
            --input-border: #e0e0e0;
            --text-main: #1a1a1a;
            --text-secondary: #444;
            --error-bg: #ffeaea;
            --error-text: #d12e00;
        }
        html, body {
            height: 100%;
            margin: 0;
            padding: 0;
            background: var(--bg);
            font-family: 'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: var(--text-main);
        }
        .main-container {
            max-width: 480px;
            margin: 48px auto 0 auto;
            background: var(--container-bg);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            padding: 40px 28px 32px 28px;
            text-align: center;
            position: relative;
        }
        .title {
            font-size: 2.2rem;
            font-weight: 700;
            color: var(--primary);
            margin-bottom: 8px;
            letter-spacing: -1px;
        }
        .subtitle {
            color: var(--text-secondary);
            font-size: 1.08rem;
            margin-bottom: 28px;
        }
        .input-row {
            display: flex;
            justify-content: center;
            align-items: center;
            margin-bottom: 28px;
            gap: 0;
            position: relative;
        }
        .url-input {
            flex: 1;
            padding: 15px 16px;
            font-size: 1.08rem;
            border: 1.5px solid var(--input-border);
            border-radius: 8px 0 0 8px;
            outline: none;
            background: var(--input-bg);
            transition: border 0.2s;
        }
        .url-input:focus {
            border-color: var(--primary);
        }
        .copy-btn {
            background: var(--container-bg);
            border: 1.5px solid var(--input-border);
            border-left: none;
            padding: 0 14px;
            font-size: 1.2rem;
            cursor: pointer;
            border-radius: 0;
            height: 48px;
            transition: background 0.2s, border 0.2s;
        }
        .copy-btn:active {
            background: var(--primary-light);
        }
        .download-btn {
            background: linear-gradient(90deg, var(--primary) 70%, var(--primary-light) 100%);
            color: #fff;
            border: none;
            padding: 0 28px;
            font-size: 1.08rem;
            font-weight: 600;
            border-radius: 0 8px 8px 0;
            cursor: pointer;
            height: 48px;
            transition: background 0.2s, box-shadow 0.2s;
            box-shadow: 0 2px 8px rgba(255,60,0,0.08);
        }
        .download-btn:disabled {
            background: var(--primary-light);
            cursor: not-allowed;
        }
        .download-btn:hover:not(:disabled) {
            background: linear-gradient(90deg, #d12e00 70%, var(--primary-light) 100%);
        }
        .spinner {
            display: none;
            position: absolute;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            width: 28px;
            height: 28px;
            border: 3px solid var(--primary-light);
            border-top: 3px solid var(--primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            z-index: 2;
        }
        @keyframes spin {
            0% { transform: translate(-50%, -50%) rotate(0deg); }
            100% { transform: translate(-50%, -50%) rotate(360deg); }
        }
        .song-info-box {
            display: none;
            margin: 36px auto 0 auto;
            background: #f7fbfa;
            border-radius: 14px;
            padding: 32px 18px 10px 18px;
            max-width: 100%;
            box-shadow: 0 4px 24px rgba(0,0,0,0.04);
        }
        .song-info-centered {
            display: flex;
            flex-direction: column;
            align-items: center;
            margin-bottom: 24px;
        }
        .song-cover {
            width: 140px;
            height: 140px;
            border-radius: 12px;
            object-fit: cover;
            box-shadow: 0 4px 16px rgba(0,0,0,0.10);
            margin-bottom: 14px;
            background: #eee;
        }
        .song-title {
            font-size: 1.15rem;
            font-weight: 600;
            color: var(--text-main);
            margin-bottom: 4px;
            text-align: center;
        }
        .song-meta {
            color: #666;
            font-size: 0.98rem;
            text-align: center;
        }
        .song-list-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 14px 0 14px 0;
            border-top: 1px solid #eee;
            border-bottom: 1px solid #eee;
            margin-top: 12px;
        }
        .song-list-index {
            color: var(--primary);
            font-weight: 700;
            font-size: 1.05rem;
            margin-right: 8px;
        }
        .song-list-title {
            color: var(--primary);
            font-size: 1.05rem;
            font-weight: 500;
            flex: 1;
            text-align: left;
        }
        .song-list-meta {
            color: #888;
            font-size: 0.98rem;
            margin-left: 8px;
        }
        .song-list-download-btn {
            background: var(--primary);
            color: #fff;
            border: none;
            padding: 8px 22px;
            font-size: 1.05rem;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .song-list-download-btn:disabled {
            background: var(--primary-light);
            cursor: not-allowed;
        }
        .song-list-download-btn:hover:not(:disabled) {
            background: #d12e00;
        }
        .progress-section {
            display: none;
            margin-top: 24px;
        }
        .progress-bar {
            width: 100%;
            background: #eee;
            border-radius: 8px;
            overflow: hidden;
            height: 16px;
            margin-bottom: 8px;
        }
        .progress-inner {
            height: 100%;
            background: linear-gradient(90deg, var(--primary) 60%, var(--primary-light) 100%);
            width: 0%;
            transition: width 0.4s;
        }
        .progress-label {
            color: #444;
            font-size: 0.98rem;
        }
        .final-buttons {
            display: none;
            flex-direction: column;
            gap: 14px;
            margin-top: 24px;
        }
        .final-btn {
            background: var(--primary);
            color: #fff;
            border: none;
            padding: 14px 0;
            font-size: 1.08rem;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            width: 100%;
            transition: background 0.2s;
        }
        .final-btn:hover {
            background: #d12e00;
        }
        .final-btn:disabled {
            background: var(--primary-light);
            cursor: not-allowed;
        }
        .error {
            background: var(--error-bg);
            color: var(--error-text);
            padding: 13px;
            border-radius: 8px;
            margin-top: 18px;
            display: none;
            font-weight: 600;
            font-size: 1.01rem;
            box-shadow: 0 2px 8px rgba(255,60,0,0.04);
        }
        .fetch-progress-bar {
            width: 60%;
            margin: 18px auto 0 auto;
            background: #e8f1ef;
            border-radius: 8px;
            height: 12px;
            overflow: hidden;
            box-shadow: 0 1px 4px rgba(0,0,0,0.03);
            display: none;
        }
        .fetch-progress-inner {
            height: 100%;
            background: linear-gradient(90deg, var(--primary) 60%, var(--primary-light) 100%);
            width: 1%;
            transition: width 0.3s;
        }
        .download-status {
            color: #666;
            font-size: 0.93rem;
            margin-top: 8px;
            font-style: italic;
        }
        @media (max-width: 600px) {
            .main-container {
                padding: 14px 2px 14px 2px;
            }
            .song-info-centered {
                flex-direction: column;
                gap: 8px;
            }
            .song-cover {
                width: 80px;
                height: 80px;
            }
        }
        /* Accessibility focus */
        .url-input:focus, .copy-btn:focus, .download-btn:focus, .song-list-download-btn:focus, .final-btn:focus {
            outline: 2px solid var(--primary);
            outline-offset: 2px;
        }
    </style>
</head>
<body>
    <div class="main-container" aria-label="SoundCloud MP3 Downloader">
        <div id="mainState">
            <div class="title">SoundCloud MP3 Downloader</div>
            <div class="subtitle">Download SoundCloud to MP3 Online for Free – Works on All Devices</div>
            <div class="input-row">
                <input type="text" class="url-input" id="urlInput" placeholder="Paste SoundCloud URL" autocomplete="off" aria-label="SoundCloud URL">
                <button class="copy-btn" onclick="copyUrl()" title="Copy" id="copyBtn" aria-label="Copy URL"><span>📋</span></button>
                <button class="download-btn" id="fetchBtn" onclick="fetchSong()" aria-label="Download">Download</button>
                <div class="spinner" id="fetchSpinner" aria-label="Loading"></div>
            </div>
        </div>
        <div class="song-info-box" id="songInfoBox">
            <div class="song-info-centered">
                <img src="" alt="Cover" class="song-cover" id="songCover" style="display:none;">
                <div class="song-title" id="songTitle"></div>
                <div class="song-meta" id="songMeta"></div>
                <div class="download-status" id="downloadStatus"></div>
                <div class="fetch-progress-bar" id="fetchProgressBar">
                    <div class="fetch-progress-inner" id="fetchProgressInner"></div>
                </div>
            </div>
            <div class="song-list-row">
                <span class="song-list-index">1:</span>
                <span class="song-list-title" id="songListTitle"></span>
                <span class="song-list-meta" id="songListMeta"></span>
                <button class="song-list-download-btn" id="songListDownloadBtn" onclick="checkDownloadStatus()" aria-label="Start Download">Download</button>
            </div>
        </div>
        <div class="progress-section" id="progressSection">
            <div class="progress-bar">
                <div class="progress-inner" id="progressInner"></div>
            </div>
            <div class="progress-label" id="progressLabel">Preparing download...</div>
        </div>
        <div class="final-buttons" id="finalButtons">
            <button class="final-btn" id="mp3Btn" aria-label="Download MP3">Download MP3</button>
            <button class="final-btn" id="coverBtn" aria-label="Download Cover">Download Cover [HD]</button>
            <button class="final-btn" id="anotherBtn" aria-label="Download Another Song">Download Another Song</button>
        </div>
        <div class="error" id="error" role="alert"></div>
    </div>
    <script>
        let songData = null;
        let fetchProgressInterval = null;
        let downloadCheckInterval = null;
        
        function copyUrl() {
            const urlInput = document.getElementById('urlInput');
            urlInput.select();
            document.execCommand('copy');
        }
        
        function showError(msg) {
            const err = document.getElementById('error');
            err.textContent = msg;
            err.style.display = 'block';
        }
        
        function hideError() {
            document.getElementById('error').style.display = 'none';
        }
        
        function setFetchingState(isFetching) {
            document.getElementById('urlInput').disabled = isFetching;
            document.getElementById('fetchBtn').disabled = isFetching;
            document.getElementById('copyBtn').disabled = isFetching;
            document.getElementById('fetchSpinner').style.display = isFetching ? 'block' : 'none';
        }
        
        function resetUI() {
            document.getElementById('mainState').style.display = '';
            document.getElementById('songInfoBox').style.display = 'none';
            document.getElementById('progressSection').style.display = 'none';
            document.getElementById('finalButtons').style.display = 'none';
            setFetchingState(false);
            stopFetchProgressBar();
            hideError();
            document.getElementById('urlInput').value = '';
            if (downloadCheckInterval) {
                clearInterval(downloadCheckInterval);
                downloadCheckInterval = null;
            }
        }
        
        function animateFetchProgressBar() {
            const bar = document.getElementById('fetchProgressBar');
            const inner = document.getElementById('fetchProgressInner');
            bar.style.display = 'block';
            let progress = 1;
            inner.style.width = progress + '%';
            if (fetchProgressInterval) clearInterval(fetchProgressInterval);
            fetchProgressInterval = setInterval(() => {
                if (progress < 80) {
                    progress += Math.random() * 8 + 2;
                } else if (progress < 95) {
                    progress += Math.random() * 2 + 0.5;
                } else {
                    progress += Math.random() * 0.5;
                }
                if (progress > 99) progress = 99;
                inner.style.width = progress + '%';
            }, 180);
        }
        
        function stopFetchProgressBar() {
            const bar = document.getElementById('fetchProgressBar');
            const inner = document.getElementById('fetchProgressInner');
            if (fetchProgressInterval) clearInterval(fetchProgressInterval);
            inner.style.width = '100%';
            setTimeout(() => {
                bar.style.display = 'none';
                inner.style.width = '1%';
            }, 400);
        }
        
        function updateDownloadStatus(status) {
            const statusEl = document.getElementById('downloadStatus');
            statusEl.textContent = status;
        }
        
        function fetchSong() {
            const url = document.getElementById('urlInput').value.trim();
            if (!url) {
                showError('Please enter a SoundCloud URL');
                return;
            }
            if (!url.includes('soundcloud.com')) {
                showError('Please enter a valid SoundCloud URL');
                return;
            }
            hideError();
            setFetchingState(true);
            document.getElementById('mainState').style.display = 'none';
            document.getElementById('songInfoBox').style.display = 'block';
            document.getElementById('progressSection').style.display = 'none';
            document.getElementById('finalButtons').style.display = 'none';
            
            document.getElementById('songCover').style.display = 'none';
            document.getElementById('songTitle').textContent = 'Fetching track info...';
            document.getElementById('songTitle').style.display = 'block';
            document.getElementById('songMeta').textContent = '';
            document.getElementById('songMeta').style.display = 'none';
            document.getElementById('downloadStatus').textContent = '';
            document.getElementById('songListTitle').textContent = '';
            document.getElementById('songListMeta').textContent = '';
            document.getElementById('songListDownloadBtn').disabled = true;
            
            animateFetchProgressBar();
            
            fetch('/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            })
            .then(res => res.json())
            .then(data => {
                setFetchingState(false);
                stopFetchProgressBar();
                if (data.success) {
                    songData = data;
                    if (data.cover_url) {
                        document.getElementById('songCover').src = data.cover_url;
                        document.getElementById('songCover').style.display = '';
                    } else {
                        document.getElementById('songCover').style.display = 'none';
                    }
                    document.getElementById('songTitle').textContent = data.title;
                    document.getElementById('songTitle').style.display = 'block';
                    document.getElementById('songMeta').textContent = '';
                    document.getElementById('songMeta').style.display = 'block';
                    document.getElementById('songListTitle').textContent = data.title;
                    document.getElementById('songListMeta').textContent = '';
                    document.getElementById('songListDownloadBtn').disabled = false;
                    
                    updateDownloadStatus('Download ready');
                } else {
                    showError(data.error || 'Failed to fetch track');
                    resetUI();
                }
            })
            .catch(() => {
                setFetchingState(false);
                stopFetchProgressBar();
                showError('Network error. Please try again.');
                resetUI();
            });
        }
        
        function checkDownloadStatus() {
            if (!songData) return;
            
            document.getElementById('songInfoBox').style.display = 'none';
            document.getElementById('progressSection').style.display = 'block';
            document.getElementById('finalButtons').style.display = 'none';
            
            // Start async download
            fetch('/start_download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    url: songData.original_url,
                    track_id: songData.track_id 
                })
            })
            .catch(error => {
                console.error('Error starting download:', error);
                showError('Failed to start download');
                resetUI();
                return;
            });
            
            // Start checking download progress
            let progress = 0;
            let consecutiveErrors = 0;
            downloadCheckInterval = setInterval(() => {
                fetch(`/download_progress/${songData.track_id}`)
                .then(res => {
                    if (!res.ok) {
                        throw new Error(`HTTP ${res.status}`);
                    }
                    return res.json();
                })
                .then(data => {
                    consecutiveErrors = 0; // Reset error counter on success
                    
                    if (data.status === 'completed') {
                        document.getElementById('progressInner').style.width = '100%';
                        document.getElementById('progressLabel').textContent = 'Download completed!';
                        clearInterval(downloadCheckInterval);
                        setTimeout(showFinalButtons, 500);
                    } else if (data.status === 'downloading') {
                        progress = Math.max(progress, data.progress || 0);
                        document.getElementById('progressInner').style.width = progress + '%';
                        document.getElementById('progressLabel').textContent = `Downloading... ${progress}%`;
                    } else if (data.status === 'error') {
                        clearInterval(downloadCheckInterval);
                        showError(data.error || 'Download failed');
                        resetUI();
                    } else {
                        // Still preparing/waiting
                        progress = Math.min(progress + 2, 15);
                        document.getElementById('progressInner').style.width = progress + '%';
                        document.getElementById('progressLabel').textContent = 'Preparing download...';
                    }
                })
                .catch(error => {
                    console.error('Progress check error:', error);
                    consecutiveErrors++;
                    
                    // If too many consecutive errors, stop trying
                    if (consecutiveErrors >= 5) {
                        clearInterval(downloadCheckInterval);
                        showError('Lost connection to server');
                        resetUI();
                        return;
                    }
                    
                    // Keep trying on network errors but slow down progress
                    progress = Math.min(progress + 0.5, 10);
                    document.getElementById('progressInner').style.width = progress + '%';
                    document.getElementById('progressLabel').textContent = 'Connecting...';
                });
            }, 1500); // Increased interval to reduce server load
        }
        
        function showFinalButtons() {
            document.getElementById('progressSection').style.display = 'none';
            document.getElementById('finalButtons').style.display = 'flex';
            
            // Check if files are ready and enable/disable buttons accordingly
            checkFileAvailability();
        }
        
        function checkFileAvailability() {
            if (!songData) return;
            
            fetch(`/download_progress/${songData.track_id}`)
            .then(res => res.json())
            .then(data => {
                const mp3Btn = document.getElementById('mp3Btn');
                const coverBtn = document.getElementById('coverBtn');
                
                if (data.status === 'completed') {
                    mp3Btn.disabled = false;
                    coverBtn.disabled = !data.cover_available;
                } else {
                    mp3Btn.disabled = true;
                    coverBtn.disabled = true;
                }
            });
        }
        
        document.getElementById('mp3Btn').onclick = function() {
            if (songData) {
                const url = encodeURIComponent(songData.original_url);
                window.location.href = `/download_mp3/${songData.track_id}?url=${url}`;
            }
        };
        
        document.getElementById('coverBtn').onclick = function() {
            if (songData && songData.cover_ext) {
                const url = encodeURIComponent(songData.original_url);
                const cover_ext = encodeURIComponent(songData.cover_ext);
                window.location.href = `/download_cover/${songData.track_id}?url=${url}&cover_ext=${cover_ext}`;
            }
        };
        
        document.getElementById('anotherBtn').onclick = function() {
            songData = null;
            resetUI();
        };
        
        document.getElementById('urlInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                fetchSong();
            }
        });
        
        document.getElementById('urlInput').focus();
        resetUI();
    </script>
</body>
</html>'''
    return render_template_string(html_content)

@app.route('/download', methods=['POST'])
def download():
    """Handle download requests (metadata only)"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL is required'})
        if 'soundcloud.com' not in url:
            return jsonify({'success': False, 'error': 'Please provide a valid SoundCloud URL'})
        
        # Generate unique track ID
        track_id = str(uuid.uuid4())[:8]
        
        # Fetch metadata only (fast)
        result = fetch_soundcloud_metadata(url)
        if result['success']:
            response_data = {
                'success': True,
                'track_id': track_id,
                'title': result['title'],
                'cover_url': result['thumbnail_url'],
                'cover_ext': result['cover_ext'],
                'original_url': url
            }
            return jsonify(response_data)
        else:
            return jsonify({'success': False, 'error': result['error']})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'})

@app.route('/start_download', methods=['POST'])
def start_download():
    """Start asynchronous download of MP3 and cover"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        track_id = data.get('track_id', '').strip()
        
        if not url or not track_id:
            return jsonify({'success': False, 'error': 'URL and track_id are required'})
        
        if 'soundcloud.com' not in url:
            return jsonify({'success': False, 'error': 'Please provide a valid SoundCloud URL'})
        
        # Initialize download status
        download_status[track_id] = {'status': 'starting', 'progress': 0}
        
        # Start download in background thread
        download_thread = threading.Thread(
            target=download_soundcloud_track_async, 
            args=(url, track_id),
            daemon=True
        )
        download_thread.start()
        
        return jsonify({'success': True, 'track_id': track_id})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'})

@app.route('/download_progress/<track_id>')
def download_progress(track_id):
    """Check download progress for a track"""
    try:
        if track_id not in download_status:
            return jsonify({'status': 'not_found', 'progress': 0})
        
        status_data = download_status[track_id].copy()
        
        # Check if files actually exist
        if status_data.get('status') == 'completed':
            mp3_path = os.path.join(DOWNLOAD_DIR, f"{track_id}.mp3")
            cover_path = status_data.get('cover_path')
            
            status_data['mp3_available'] = os.path.exists(mp3_path)
            status_data['cover_available'] = cover_path and os.path.exists(cover_path)
        
        return jsonify(status_data)
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e), 'progress': 0})

@app.route('/download_file/<filename>')
def download_file(filename):
    """Serve downloaded files"""
    try:
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download_mp3/<track_id>')
def download_mp3(track_id):
    """Download and serve the MP3 file for the given track_id. Requires ?url=..."""
    try:
        url = request.args.get('url', '').strip()
        if not url or 'soundcloud.com' not in url:
            return jsonify({'error': 'Missing or invalid url parameter'}), 400
        
        mp3_filename = f"{track_id}.mp3"
        mp3_path = os.path.join(DOWNLOAD_DIR, mp3_filename)
        
        # Check if file exists from async download
        if os.path.exists(mp3_path):
            try:
                return send_file(mp3_path, as_attachment=True, download_name=f"{track_id}.mp3")
            except Exception as e:
                print(f"Error serving file: {e}")
                return jsonify({'error': 'File serving error'}), 500
        
        # If not available yet, check download status
        if track_id in download_status:
            status = download_status[track_id].get('status')
            if status == 'downloading':
                return jsonify({'error': 'Download still in progress. Please wait.'}), 202
            elif status == 'error':
                return jsonify({'error': download_status[track_id].get('error', 'Download failed')}), 500
        
        # Fall back to synchronous download if async failed
        try:
            download_soundcloud_track_async(url, track_id)
            # Wait a bit for the download to complete
            max_wait = 30  # 30 seconds max wait
            wait_time = 0
            while wait_time < max_wait:
                if os.path.exists(mp3_path):
                    return send_file(mp3_path, as_attachment=True, download_name=f"{track_id}.mp3")
                time.sleep(1)
                wait_time += 1
            
            return jsonify({'error': 'Download timeout'}), 408
        except Exception as e:
            print(f"Fallback download error: {e}")
            return jsonify({'error': f'Download failed: {str(e)}'}), 500
            
    except Exception as e:
        print(f"Download MP3 error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/download_cover/<track_id>')
def download_cover(track_id):
    """Download and serve the cover image for the given track_id. Requires ?url=...&cover_ext=..."""
    try:
        url = request.args.get('url', '').strip()
        cover_ext = request.args.get('cover_ext', 'jpg')
        if not url or 'soundcloud.com' not in url:
            return jsonify({'error': 'Missing or invalid url parameter'}), 400
        
        cover_filename = f"{track_id}_cover.{cover_ext}"
        cover_path = os.path.join(DOWNLOAD_DIR, cover_filename)
        
        # Check if file exists from async download
        if os.path.exists(cover_path):
            try:
                return send_file(cover_path, as_attachment=True, download_name=cover_filename)
            except Exception as e:
                print(f"Error serving cover file: {e}")
                return jsonify({'error': 'File serving error'}), 500
        
        # If not available yet, check download status
        if track_id in download_status:
            status = download_status[track_id].get('status')
            if status == 'downloading':
                return jsonify({'error': 'Download still in progress. Please wait.'}), 202
            elif status == 'error':
                return jsonify({'error': download_status[track_id].get('error', 'Download failed')}), 500
        
        # Fall back to synchronous download if async failed
        try:
            download_soundcloud_track_async(url, track_id)
            # Wait a bit for the download to complete
            max_wait = 30  # 30 seconds max wait
            wait_time = 0
            while wait_time < max_wait:
                if os.path.exists(cover_path):
                    return send_file(cover_path, as_attachment=True, download_name=cover_filename)
                time.sleep(1)
                wait_time += 1
            
            return jsonify({'error': 'Cover download timeout'}), 408
        except Exception as e:
            print(f"Fallback cover download error: {e}")
            return jsonify({'error': f'Cover download failed: {str(e)}'}), 500
            
    except Exception as e:
        print(f"Download cover error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

@app.after_request
def add_header(response):
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    return response

if __name__ == '__main__':
    print("🎵 SoundCloud Downloader Server Starting...")
    print(f"📁 Downloads will be saved to: {os.path.abspath(DOWNLOAD_DIR)}")
    print("🌐 Server starting...")
    print("🧹 File cleanup: Files older than 1 hour will be automatically deleted")
    
    # Use environment variables for production
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    if debug:
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        # Production mode
        import gunicorn.app.wsgiapp as wsgi
        # This will be handled by gunicorn in production
        app.run(host='0.0.0.0', port=port, debug=False)