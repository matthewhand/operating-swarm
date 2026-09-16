// Agent creator page logic (loaded via {% static %} from agent_creator.html).
let generatedCode = '';
let validationResult = null;

function generateAgentCode() {
    const form = document.getElementById('agentForm');
    const formData = new FormData(form);

    // Convert form data to JSON
    const data = {};
    for (let [key, value] of formData.entries()) {
        if (key === 'expertise') {
            // Handle multiple select
            const selected = Array.from(document.getElementById('expertise').selectedOptions)
                                 .map(option => option.value);
            data[key] = selected;
        } else if (key === 'tags') {
            // Handle comma-separated tags
            data[key] = value.split(',').map(tag => tag.trim()).filter(tag => tag);
        } else {
            data[key] = value;
        }
    }

    // Validate required fields
    if (!data.name || !data.description || !data.instructions) {
        showMessage('Please fill in all required fields (marked with *)', 'danger');
        return;
    }
    data.assist = true

    showMessage('Generating BlueprintBase class (default LLM, then template fallback)...', 'info');

    fetch('/agent-creator/generate/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            generatedCode = result.code;
            validationResult = result.validation;
            displayCode(result.code);
            displayValidation(result.validation);
            const validateBtn = document.getElementById('validateBtn');
            validateBtn.disabled = false;
            validateBtn.classList.remove('d-none', 'btn-outline-secondary');
            validateBtn.classList.add('btn-outline-primary');

            if (result.validation.valid) {
                const saveBtn = document.getElementById('saveBtn');
                saveBtn.disabled = false;
                saveBtn.classList.remove('d-none', 'btn-outline-secondary');
                saveBtn.classList.add('btn-success');
                showMessage('Agent code generated and validated successfully!', 'success');
            } else {
                showMessage('Agent code generated but has validation issues. Check the validation results.', 'warning');
            }
        } else {
            showMessage('Error: ' + result.error, 'danger');
        }
    })
    .catch(error => {
        showMessage('Network error: ' + error.message, 'danger');
    });
}

function displayCode(code) {
    const container = document.getElementById('codeContainer');
    container.innerHTML = `<pre><code class="language-python">${escapeHtml(code)}</code></pre>`;
    if (window.Prism) Prism.highlightElement(container.querySelector('code'));
}

function displayValidation(validation) {
    const container = document.getElementById('validationContent');
    const resultsDiv = document.getElementById('validationResults');

    let html = '';

    // Overall status
    if (validation.valid) {
        html += '<div class="alert alert-success">✅ Code is valid and ready to use!</div>';
    } else {
        html += '<div class="alert alert-danger">❌ Code has validation issues</div>';
    }

    // Detailed results
    html += '<div class="row">';
    html += `<div class="col-4"><strong>Syntax:</strong> ${validation.syntax_valid ? '✅' : '❌'}</div>`;
    html += `<div class="col-4"><strong>Structure:</strong> ${validation.structure_valid ? '✅' : '❌'}</div>`;
    html += `<div class="col-4"><strong>Linting:</strong> ${validation.lint_clean ? '✅' : '⚠️'}</div>`;
    html += '</div>';

    // Errors
    if (validation.errors.length > 0) {
        html += '<div class="mt-3"><strong>Errors:</strong><ul class="text-danger">';
        validation.errors.forEach(error => {
            html += `<li>${escapeHtml(error)}</li>`;
        });
        html += '</ul></div>';
    }

    // Warnings
    if (validation.warnings.length > 0) {
        html += '<div class="mt-3"><strong>Warnings:</strong><ul class="text-warning">';
        validation.warnings.forEach(warning => {
            html += `<li>${escapeHtml(warning)}</li>`;
        });
        html += '</ul></div>';
    }

    container.innerHTML = html;
    resultsDiv.classList.remove('os-hide');
}

function validateCode() {
    if (!generatedCode) {
        showMessage('No code to validate. Generate code first.', 'warning');
        return;
    }

    showMessage('Validating code...', 'info');

    fetch('/agent-creator/validate/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({code: generatedCode})
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            validationResult = result.validation;
            displayValidation(result.validation);

            if (result.validation.valid) {
                const saveBtn = document.getElementById('saveBtn');
                saveBtn.disabled = false;
                saveBtn.classList.remove('d-none', 'btn-outline-secondary');
                saveBtn.classList.add('btn-success');
                showMessage('Code validation passed!', 'success');
            } else {
                showMessage('Code validation found issues. Check the results below.', 'warning');
            }
        } else {
            showMessage('Validation error: ' + result.error, 'danger');
        }
    })
    .catch(error => {
        showMessage('Network error: ' + error.message, 'danger');
    });
}

function saveAgent() {
    if (!generatedCode || !validationResult || !validationResult.valid) {
        showMessage('Cannot save invalid code. Please fix validation issues first.', 'danger');
        return;
    }

    const agentName = document.getElementById('agentName').value;
    const agentDescription = document.getElementById('agentDescription').value;

    showMessage('Saving agent...', 'info');

    fetch('/agent-creator/save/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({
            code: generatedCode,
            name: agentName,
            description: agentDescription
        })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            showMessage(result.message || `Agent "${agentName}" saved successfully! Path: ${result.path}`, 'success');
        } else {
            showMessage('Save error: ' + result.error, 'danger');
        }
    })
    .catch(error => {
        showMessage('Network error: ' + error.message, 'danger');
    });
}

function clearForm() {
    document.getElementById('agentForm').reset();
    document.getElementById('codeContainer').innerHTML = `
        <div class="ac-empty">
            <i class="fas fa-code" aria-hidden="true"></i>
            <p>No code generated yet</p>
            <div class="os-meta">Fill out the form and click <strong>Generate Agent Code</strong> — the Python blueprint will appear here.</div>
            <div class="ac-skeleton" aria-hidden="true"><div></div><div></div><div></div><div></div><div></div></div>
        </div>
    `;
    document.getElementById('validationResults').classList.add('os-hide');
    const validateBtn = document.getElementById('validateBtn');
    const saveBtn = document.getElementById('saveBtn');
    validateBtn.disabled = true;
    saveBtn.disabled = true;
    validateBtn.classList.add('d-none', 'btn-outline-secondary');
    validateBtn.classList.remove('btn-outline-primary');
    saveBtn.classList.add('d-none', 'btn-outline-secondary');
    saveBtn.classList.remove('btn-success');
    generatedCode = '';
    validationResult = null;
    clearMessages();
}

function getCSRFToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}

function showMessage(message, type) {
    const container = document.getElementById('statusMessages');
    const alertClass = `alert-${type}`;
    const role = (type === 'danger' || type === 'warning') ? 'alert' : 'status';
    container.innerHTML = `<div class="alert ${alertClass} alert-dismissible fade show" role="${role}">
        ${escapeHtml(message)}
        <button type="button" class="btn-close" aria-label="Close" data-bs-dismiss="alert"></button>
    </div>`;
}

function clearMessages() {
    document.getElementById('statusMessages').innerHTML = '';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

const AGENT_CREATOR_ACTIONS = {
    'generate-agent': generateAgentCode,
    'clear-form': clearForm,
    'validate-code': validateCode,
    'save-agent': saveAgent,
};

document.querySelector('.ac-wrap')?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-action]');
    if (!btn || !event.currentTarget.contains(btn)) return;
    const handler = AGENT_CREATOR_ACTIONS[btn.getAttribute('data-action')];
    if (typeof handler === 'function') handler();
});
