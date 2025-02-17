let editor;
let currentFile = 'index.html';
let files = {
    'index.html': null,
    'styles.css': null,
    'script.js': null
};

const fileExtToMode = {
    'html': 'html',
    'css': 'css',
    'js': 'javascript'
};

document.addEventListener('DOMContentLoaded', async function() {
    editor = CodeMirror.fromTextArea(document.getElementById('code'), {
        mode: 'html',
        theme: 'ayu-dark',
        lineNumbers: true,
        autoCloseTags: true,
        autoCloseBrackets: true,
        matchBrackets: true,
        indentUnit: 4,
        tabSize: 4,
        indentWithTabs: false,
        lineWrapping: true,
        extraKeys: {
            'Ctrl-S': saveCurrentFile,
            'Cmd-S': saveCurrentFile
        }
    });

    await Promise.all([
        loadFile('index.html'),
        loadFile('styles.css'),
        loadFile('script.js')
    ]);

    const fileButtons = document.querySelectorAll('.file-tab');
    fileButtons.forEach(btn => {
        btn.addEventListener('click', () => switchFile(btn.dataset.filename));
    });

    switchFile('index.html');

    editor.on('change', debounce(updatePreview, 1000));

    document.getElementById('deploy-btn').addEventListener('click', deploySite);

    updatePreview();
});

async function loadFile(filename) {
    const siteId = document.getElementById('site-id').value;
    try {
        const response = await fetch(`/api/sites/${siteId}/files/${filename}`);
        if (!response.ok) throw new Error(`Failed to load ${filename}`);
        const data = await response.json();
        files[filename] = data.content;
    } catch (error) {
        console.error(`Error loading ${filename}:`, error);
        showNotification(`Error loading ${filename}`, 'error');
    }
}

function switchFile(filename) {
    files[currentFile] = editor.getValue();

    const ext = filename.split('.').pop();
    editor.setOption('mode', fileExtToMode[ext]);

    currentFile = filename;
    editor.setValue(files[filename] || '');

    document.querySelectorAll('.file-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filename === filename);
    });
}

async function saveCurrentFile() {
    const siteId = document.getElementById('site-id').value;
    const content = editor.getValue();
    files[currentFile] = content;

    try {
        const response = await fetch(`/api/sites/${siteId}/files/${currentFile}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ content })
        });

        if (!response.ok) throw new Error(`Failed to save ${currentFile}`);
        showNotification(`${currentFile} saved successfully`, 'success');
    } catch (error) {
        console.error(`Error saving ${currentFile}:`, error);
        showNotification(`Error saving ${currentFile}`, 'error');
    }
}

function updatePreview() {
    const previewFrame = document.getElementById('preview-frame');
    if (!previewFrame) return;

    const doc = previewFrame.contentDocument || previewFrame.contentWindow.document;
    doc.open();
    doc.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <style>${files['styles.css']}</style>
        </head>
        <body>
            ${files['index.html']}
            <script>${files['script.js']}</script>
        </body>
        </html>
    `);
    doc.close();
}

async function deploySite() {
    const siteId = document.getElementById('site-id').value;
    
    await saveCurrentFile();

    try {
        const response = await fetch(`/api/sites/${siteId}/deploy`, {
            method: 'POST'
        });

        if (!response.ok) throw new Error('Failed to deploy site');
        
        const data = await response.json();
        showDeployModal(data.url);
    } catch (error) {
        console.error('Error deploying site:', error);
        showNotification('Error deploying site', 'error');
    }
}

function showDeployModal(siteUrl) {
    const modal = document.createElement('div');
    modal.className = 'modal show-modal';
    modal.innerHTML = `
        <div class="modal-content">
            <h2>Site Deployed Successfully!</h2>
            <p>Your site is now live at:</p>
            <div class="site-url">
                <input type="text" value="${siteUrl}" readonly>
                <button onclick="navigator.clipboard.writeText('${siteUrl}')">Copy</button>
            </div>
            <div class="modal-buttons">
                <a href="${siteUrl}" target="_blank" class="btn primary">View Site</a>
                <button onclick="this.closest('.modal').remove()" class="btn">Close</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
