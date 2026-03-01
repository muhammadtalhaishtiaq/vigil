/* ═══════════════════════════════════════════════════
   VIGIL PROFILE PAGE — Dynamic Form Integration
═══════════════════════════════════════════════════ */

let profileState = {
  current: null,
  isLoading: false,
  isDirty: false
};

/* ── LOAD PROFILE ON PAGE LOAD ── */
async function loadProfile() {
  try {
    profileState.isLoading = true;
    const response = await fetch('/api/profile/load');
    const data = await response.json();
    
    profileState.current = data;
    populateFormFromProfile(data);
    updateCompletenessBar(data.completeness || 0);
    updatePreview(data);
    
    // Mark as clean after load
    profileState.isDirty = false;
    
  } catch (error) {
    console.error('Error loading profile:', error);
    showToast('Error loading profile', 'error');
  } finally {
    profileState.isLoading = false;
  }
}

/* ── POPULATE FORM FROM PROFILE ── */
function populateFormFromProfile(profile) {
  if (!profile) return;
  
  // Map profile fields to form inputs
  const fieldMap = {
    'company_name': 'input[name="company_name"]',
    'location': 'input[name="location"]',
    'industry': 'input[name="industry"]',
    'stage': 'select[name="stage"]',
    'arb': 'input[name="arb"]',
    'employees': 'input[name="employees"]',
    'description': 'textarea[name="description"]'
  };
  
  for (const [profileKey, selector] of Object.entries(fieldMap)) {
    const element = document.querySelector(selector);
    if (element && profile[profileKey]) {
      element.value = profile[profileKey];
    }
  }
  
  // Handle tags as chips
  if (profile.tags && Array.isArray(profile.tags)) {
    const tagChips = document.querySelectorAll('.chip-opt');
    tagChips.forEach(chip => {
      if (profile.tags.includes(chip.textContent.trim())) {
        chip.classList.add('sel');
      } else {
        chip.classList.remove('sel');
      }
    });
  }
}

/* ── UPDATE PREVIEW CARD ── */
function updatePreview(profile) {
  if (!profile) return;
  
  const pvName = document.querySelector('.pv-name');
  const pvSub = document.querySelector('.pv-sub');
  const pvTags = document.querySelector('.pv-tags');
  const pvCompl = document.querySelector('.pvc-pct');
  
  if (pvName) pvName.textContent = profile.company_name || 'Unnamed Company';
  if (pvSub) {
    const parts = [profile.location, profile.industry].filter(Boolean);
    pvSub.textContent = parts.join(' · ') || 'Location · Industry';
  }
  
  if (pvTags && profile.tags) {
    pvTags.innerHTML = profile.tags.map(tag => {
      let className = 'gr';
      if (tag.includes('Exposed') || tag.includes('MiCA')) className = 're';
      else if (tag.includes('Raising')) className = 'or';
      else if (tag.includes('runway')) className = 'nt';
      return `<div class="pv-tag ${className}">${tag}</div>`;
    }).join('');
  }
  
  if (pvCompl) {
    const comp = profile.completeness || 0;
    pvCompl.textContent = comp + '%';
    pvCompl.style.color = comp >= 80 ? 'var(--g)' : comp >= 50 ? 'var(--or)' : 'var(--re)';
  }
}

/* ── UPDATE COMPLETENESS BAR ── */
function updateCompletenessBar(percentage) {
  const compFill = document.querySelector('.comp-fill');
  const compPct = document.querySelector('.comp-pct');
  const pvcFill = document.querySelector('.pvc-fill');
  
  if (compFill) {
    compFill.style.width = percentage + '%';
    compFill.style.background = percentage >= 80 ? 'var(--g)' : percentage >= 50 ? 'var(--or)' : 'var(--re)';
  }
  
  if (compPct) {
    compPct.textContent = percentage + '%';
    compPct.style.color = percentage >= 80 ? 'var(--g)' : percentage >= 50 ? 'var(--or)' : 'var(--re)';
  }
  
  if (pvcFill) {
    pvcFill.style.width = percentage + '%';
    pvcFill.style.background = percentage >= 80 ? 'var(--g)' : percentage >= 50 ? 'var(--or)' : 'var(--re)';
  }
}

/* ── GATHER FORM DATA ── */
function gatherFormData() {
  const profile = {
    company_name: document.querySelector('input[name="company_name"]')?.value || '',
    location: document.querySelector('input[name="location"]')?.value || '',
    industry: document.querySelector('input[name="industry"]')?.value || '',
    stage: document.querySelector('select[name="stage"]')?.value || '',
    arb: document.querySelector('input[name="arb"]')?.value || '',
    employees: parseInt(document.querySelector('input[name="employees"]')?.value || '0'),
    description: document.querySelector('textarea[name="description"]')?.value || '',
    tags: Array.from(document.querySelectorAll('.chip-opt.sel')).map(c => c.textContent.trim())
  };
  
  return profile;
}

/* ── SAVE PROFILE ── */
async function saveProfile() {
  try {
    const saveBtn = document.querySelector('.save-btn');
    const originalText = saveBtn?.textContent;
    
    const profile = gatherFormData();
    
    // Show loading state
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.textContent = '⏳ Saving...';
    }
    
    const response = await fetch('/api/profile/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile)
    });
    
    const result = await response.json();
    
    if (response.ok) {
      profileState.current = profile;
      profileState.isDirty = false;
      profileState.current.completeness = result.completeness;
      
      updateCompletenessBar(result.completeness);
      updatePreview(profileState.current);
      
      showToast('✓ Profile saved successfully!');
      
      // Redirect back to dashboard after 1 second
      setTimeout(() => {
        window.location.href = '/dashboard';
      }, 1000);
    } else {
      showToast('Error saving profile: ' + (result.detail || 'Unknown error'), 'error');
    }
  } catch (error) {
    console.error('Error saving profile:', error);
    showToast('Network error: ' + error.message, 'error');
  } finally {
    const saveBtn = document.querySelector('.save-btn');
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = originalText || '💾 Save Profile';
    }
  }
}

/* ── CHIP SELECTION (TAGS) ── */
function setupChipSelection() {
  const chips = document.querySelectorAll('.chip-opt');
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      chip.classList.toggle('sel');
      profileState.isDirty = true;
      
      // Update preview
      const profile = gatherFormData();
      updatePreview(profile);
    });
  });
}

/* ── TOAST NOTIFICATION ── */
function showToast(message, type = 'success') {
  const toast = document.querySelector('.toast');
  if (!toast) return;
  
  toast.textContent = message;
  toast.style.background = type === 'error' ? 'var(--re)' : 'var(--g)';
  toast.style.color = type === 'error' ? '#fff' : '#000';
  toast.classList.add('show');
  
  setTimeout(() => {
    toast.classList.remove('show');
  }, 3000);
}

/* ── FORM CHANGE DETECTION ── */
function setupFormTracking() {
  const inputs = document.querySelectorAll('input, textarea, select');
  inputs.forEach(input => {
    input.addEventListener('change', () => {
      profileState.isDirty = true;
      const profile = gatherFormData();
      updatePreview(profile);
    });
  });
}

/* ── SAMPLE DATA MODAL ── */
function showSampleData() {
  const modal = document.querySelector('.smodal');
  if (modal) {
    modal.classList.add('open');
  }
}

function closeSampleData() {
  const modal = document.querySelector('.smodal');
  if (modal) {
    modal.classList.remove('open');
  }
}

function useSampleData() {
  const sampleProfile = {
    company_name: "TechVenture AI",
    location: "San Francisco, CA",
    industry: "AI / Machine Learning",
    stage: "Series A",
    arb: "$5–10M ARR",
    employees: 45,
    description: "AI-powered platform for enterprise risk analytics and strategic decision-making.",
    tags: ["Raising", "US Market", "18–24mo runway"]
  };
  
  profileState.current = sampleProfile;
  populateFormFromProfile(sampleProfile);
  updatePreview(sampleProfile);
  closeSampleData();
  showToast('✓ Sample data loaded!');
}

/* ── INITIALIZE ON PAGE LOAD ── */
document.addEventListener('DOMContentLoaded', () => {
  // Load profile from API
  loadProfile();
  
  // Setup UI interactions
  setupChipSelection();
  setupFormTracking();
  
  // Wire up buttons
  const saveBtn = document.querySelector('.save-btn');
  if (saveBtn) {
    saveBtn.addEventListener('click', saveProfile);
  }
  
  const sampleBtn = document.querySelector('.sample-btn');
  if (sampleBtn) {
    sampleBtn.addEventListener('click', showSampleData);
  }
  
  const closeModalBtn = document.querySelector('.smodal-btn:not(.primary)');
  if (closeModalBtn) {
    closeModalBtn.addEventListener('click', closeSampleData);
  }
  
  const useSampleBtn = document.querySelector('.smodal-btn.primary');
  if (useSampleBtn) {
    useSampleBtn.addEventListener('click', useSampleData);
  }
  
  // Close modal on background click
  const modal = document.querySelector('.smodal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeSampleData();
    });
  }
});
