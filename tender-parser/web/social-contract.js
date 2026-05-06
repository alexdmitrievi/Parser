/**
 * Тендер PRO — Социальный контракт
 * Quiz + contacts modal
 */

// Contacts modal
const btnOrder = document.getElementById('btn-order-bp');
const modal = document.getElementById('contacts-modal');
const closeBtn = document.getElementById('contacts-close');

if (btnOrder && modal) {
  btnOrder.addEventListener('click', () => modal.classList.add('open'));
}
if (closeBtn && modal) {
  closeBtn.addEventListener('click', () => modal.classList.remove('open'));
}
if (modal) {
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.classList.remove('open');
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.classList.contains('open')) modal.classList.remove('open');
  });
}

// Social contract quiz
const quizMeta = [
  { id: 'q1', critical: true, tip: 'Подтвердите гражданство РФ: без этого условия одобрение обычно невозможно.' },
  { id: 'q2', critical: true, tip: 'Проверьте регистрацию в регионе подачи: это базовое требование соцзащиты.' },
  { id: 'q3', critical: true, tip: 'Сверьте доход с прожиточным минимумом по вашему региону.' },
  { id: 'q4', critical: false, tip: 'Подготовьте документы о доходах и составе семьи заранее.' },
  { id: 'q5', critical: false, tip: 'Сформулируйте конкретную бизнес-идею с понятной услугой или товаром.' },
  { id: 'q6', critical: false, tip: 'Составьте краткий бизнес-план со сметой и прогнозом выручки.' },
  { id: 'q7', critical: true, tip: 'Уточните формат регистрации: ИП или самозанятость в вашем регионе.' },
  { id: 'q8', critical: false, tip: 'Уточните в соцзащите, проводится ли тестирование компетенций в вашем регионе.' },
  { id: 'q9', critical: true, tip: 'Сделайте список целевых расходов и привяжите их к задачам бизнеса.' },
  { id: 'q10', critical: false, tip: 'Организуйте хранение чеков и договоров в отдельной папке.' },
  { id: 'q11', critical: false, tip: 'Оцените, сможете ли стабильно вести деятельность и сдавать отчетность.' },
  { id: 'q12', critical: true, tip: 'Использование средств строго по назначению — ключевое условие контракта.' }
];

const quizCalcBtn = document.getElementById('sc-quiz-calc');
const quizResetBtn = document.getElementById('sc-quiz-reset');
const quizContactBtn = document.getElementById('sc-quiz-contact');
const quizWarning = document.getElementById('sc-quiz-warning');
const quizResult = document.getElementById('sc-quiz-result');
const quizContacts = document.getElementById('sc-quiz-contacts');
const quizContactsList = document.getElementById('sc-quiz-contacts-list');

function syncSelectedQuizOptions() {
  document.querySelectorAll('.sc-quiz-options').forEach((group) => {
    group.querySelectorAll('.sc-quiz-option').forEach((label) => {
      const input = label.querySelector('input[type="radio"]');
      label.classList.toggle('selected', !!input?.checked);
    });
  });
}

document.querySelectorAll('.sc-quiz-options input[type="radio"]').forEach((radio) => {
  radio.addEventListener('change', () => {
    syncSelectedQuizOptions();
    quizWarning.classList.remove('show');
  });
});

function getQuizValue(questionId) {
  const selected = document.querySelector(`input[name="${questionId}"]:checked`);
  return selected ? selected.value : '';
}

function renderContactsFromExistingBlock() {
  if (!quizContactsList) return;
  quizContactsList.innerHTML = '';
  const rows = modal ? modal.querySelectorAll('.sc-contact-row') : [];
  rows.forEach((row) => {
    quizContactsList.appendChild(row.cloneNode(true));
  });
  quizContacts.classList.add('show');
  quizContactBtn.style.display = 'inline-flex';
}

function evaluateQuiz() {
  const unanswered = quizMeta.filter((item) => !getQuizValue(item.id));
  if (unanswered.length) {
    quizWarning.classList.add('show');
    quizResult.classList.remove('show');
    quizContacts.classList.remove('show');
    quizContactBtn.style.display = 'none';
    return;
  }

  quizWarning.classList.remove('show');
  let score = 0;
  let maxScore = 0;
  let criticalNoCount = 0;
  const tips = [];

  quizMeta.forEach((item) => {
    const value = getQuizValue(item.id);
    const weight = item.critical ? 2 : 1;
    maxScore += weight;

    if (value === 'yes') {
      score += weight;
    } else if (value === 'unknown') {
      score += weight * 0.5;
      tips.push(item.tip);
    } else {
      if (item.critical) criticalNoCount += 1;
      tips.push(item.tip);
    }
  });

  const percent = Math.round((score / maxScore) * 100);
  let level = 'medium';
  let levelTitle = 'Средняя вероятность';
  let levelText = 'Есть база для подачи, но часть условий требует доработки перед обращением в соцзащиту.';

  if (criticalNoCount >= 2 || percent < 45) {
    level = 'low';
    levelTitle = 'Низкая вероятность на текущем этапе';
    levelText = 'Сейчас есть существенные риски отказа. Рекомендуется сначала закрыть ключевые критерии и проверить документы.';
  } else if (criticalNoCount === 0 && percent >= 70) {
    level = 'high';
    levelTitle = 'Повышенная вероятность';
    levelText = 'По анкете вы близки к базовым требованиям. Следующий шаг — аккуратно подготовить пакет документов и бизнес-план.';
  }

  const uniqueTips = Array.from(new Set(tips)).slice(0, 5);
  const tipsHtml = uniqueTips.length
    ? `<ul class="sc-quiz-tips">${uniqueTips.map((tip) => `<li>${tip}</li>`).join('')}</ul>`
    : '';

  quizResult.innerHTML = `
    <div class="sc-quiz-result-badge ${level}">${levelTitle}</div>
    <div class="sc-quiz-result-title">Итоговый балл: ${percent}%</div>
    <p class="sc-quiz-result-text">${levelText}</p>
    ${tipsHtml}
    <p class="sc-quiz-disclaimer">
      Важно: результат носит предварительный информационный характер и не является юридическим заключением. Окончательное решение об одобрении принимает уполномоченный орган социальной защиты в вашем регионе.
    </p>
  `;
  quizResult.classList.add('show');
  renderContactsFromExistingBlock();
}

function resetQuiz() {
  document.querySelectorAll('.sc-quiz-options input[type="radio"]').forEach((radio) => {
    radio.checked = false;
  });
  syncSelectedQuizOptions();
  quizWarning.classList.remove('show');
  quizResult.classList.remove('show');
  quizResult.innerHTML = '';
  quizContacts.classList.remove('show');
  quizContactsList.innerHTML = '';
  quizContactBtn.style.display = 'none';
}

quizCalcBtn?.addEventListener('click', evaluateQuiz);
quizResetBtn?.addEventListener('click', resetQuiz);
quizContactBtn?.addEventListener('click', () => modal.classList.add('open'));
