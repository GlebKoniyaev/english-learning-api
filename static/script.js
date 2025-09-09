// Глобальные переменные
let currentWordId = null;
let currentWord = null;

// Показать секцию
function showSection(sectionId) {
  // Скрыть все секции
  document.querySelectorAll(".section").forEach((section) => {
    section.classList.remove("active");
  });

  // Убрать активный класс со всех кнопок
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.remove("active");
  });

  // Показать выбранную секцию
  document.getElementById(sectionId).classList.add("active");

  // Добавить активный класс кнопке
  event.target.classList.add("active");
}

// Показать сообщение
function showMessage(message, type = "info") {
  const resultDiv =
    document.getElementById("url-result") || document.createElement("div");
  resultDiv.id = "url-result";
  resultDiv.innerHTML = `<div class="message ${type}">${message}</div>`;

  if (!document.getElementById("url-result")) {
    document.getElementById("add-words").appendChild(resultDiv);
  }

  // Автоматически скрыть через 5 секунд
  setTimeout(() => {
    if (resultDiv.parentNode) {
      resultDiv.remove();
    }
  }, 5000);
}

// Обработать URL
async function processUrl() {
  const url = document.getElementById("url-input").value.trim();

  if (!url) {
    showMessage("Пожалуйста, введите URL", "error");
    return;
  }

  // Проверка валидности URL
  try {
    new URL(url);
  } catch {
    showMessage("Пожалуйста, введите корректный URL", "error");
    return;
  }

  showMessage("Обрабатываю URL...", "info");

  try {
    const response = await fetch("/process_url", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ url: url }),
    });

    const data = await response.json();

    if (response.ok) {
      showMessage(data.message, "success");
      document.getElementById("url-input").value = "";
    } else {
      showMessage(data.detail || "Ошибка при обработке URL", "error");
    }
  } catch (error) {
    showMessage("Ошибка сети: " + error.message, "error");
  }
}

// Получить следующее слово
async function getNextWord() {
  try {
    document.getElementById("current-word").textContent = "Загружаю слово...";
    document.getElementById("show-btn").style.display = "none";
    document.getElementById("answer-buttons").style.display = "none";
    document.getElementById("translations").style.display = "none";

    const response = await fetch("/next_word");
    const data = await response.json();

    if (response.ok && data.id) {
      currentWordId = data.id;
      currentWord = data;

      document.getElementById("current-word").textContent = data.name;
      document.getElementById("google-trans").textContent =
        data.translation_google || "Загружается...";
      document.getElementById("lingva-trans").textContent =
        data.translation_lingva || "Загружается...";
      document.getElementById("mymemory-trans").textContent =
        data.translation_mymemory || "Загружается...";

      // Если переводы загружаются, обновляем их
      if (
        !data.translation_google ||
        !data.translation_lingva ||
        !data.translation_mymemory
      ) {
        document.getElementById("google-trans").textContent = "Перевожу...";
        document.getElementById("lingva-trans").textContent = "Перевожу...";
        document.getElementById("mymemory-trans").textContent = "Перевожу...";

        // Ждем немного и обновляем переводы
        setTimeout(async () => {
          const updateResponse = await fetch("/next_word");
          const updateData = await updateResponse.json();
          if (updateResponse.ok && updateData.id) {
            document.getElementById("google-trans").textContent =
              updateData.translation_google || "Ошибка перевода";
            document.getElementById("lingva-trans").textContent =
              updateData.translation_lingva || "Ошибка перевода";
            document.getElementById("mymemory-trans").textContent =
              updateData.translation_mymemory || "Ошибка перевода";
          }
        }, 2000);
      }

      // Скрыть переводы и показать кнопку
      document.getElementById("translations").style.display = "none";
      document.getElementById("show-btn").style.display = "block";
      document.getElementById("answer-buttons").style.display = "none";
    } else {
      document.getElementById("current-word").textContent =
        data.message || "Нет слов для изучения";
      document.getElementById("show-btn").style.display = "none";
    }
  } catch (error) {
    document.getElementById("current-word").textContent = "Ошибка загрузки";
    showMessage("Ошибка при получении слова: " + error.message, "error");
  }
}

// Показать перевод
function showTranslation() {
  document.getElementById("translations").style.display = "block";
  document.getElementById("show-btn").style.display = "none";
  document.getElementById("answer-buttons").style.display = "flex";
}

// Ответить на слово
async function answerWord(quality) {
  if (!currentWordId) return;

  try {
    const response = await fetch(`/review_word/${currentWordId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ quality: parseInt(quality) }),
    });

    const data = await response.json();

    if (response.ok) {
      showMessage(data.message, "success");
      // Автоматически получить следующее слово через 1 секунду
      setTimeout(() => {
        getNextWord();
      }, 1000);
    } else {
      showMessage(data.detail || "Ошибка при сохранении ответа", "error");
    }
  } catch (error) {
    showMessage("Ошибка при сохранении ответа: " + error.message, "error");
  }
}

// Загрузить все слова
async function loadWords() {
  try {
    const response = await fetch("/words");
    const words = await response.json();

    const wordsList = document.getElementById("words-list");

    if (words.length === 0) {
      wordsList.innerHTML = "<p>Нет слов в базе данных</p>";
      return;
    }

    wordsList.innerHTML = words
      .map(
        (word) => `
            <div class="word-item">
                <h3>${word.name}</h3>
                <p><strong>Google:</strong> ${
                  word.translation_google || "Нет перевода"
                }</p>
                <p><strong>Lingva:</strong> ${
                  word.translation_lingva || "Нет перевода"
                }</p>
                <p><strong>MyMemory:</strong> ${
                  word.translation_mymemory || "Нет перевода"
                }</p>
                <p><strong>Уровень сложности:</strong> ${
                  word.difficulty_level
                }</p>
                <p><strong>Повторений:</strong> ${word.review_count}</p>
                <p><strong>Следующий повтор:</strong> ${
                  word.next_review_date || "Сегодня"
                }</p>
            </div>
        `
      )
      .join("");
  } catch (error) {
    showMessage("Ошибка при загрузке слов: " + error.message, "error");
  }
}

// Очистить все слова
async function clearWords() {
  if (
    !confirm(
      "Вы уверены, что хотите удалить ВСЕ слова? Это действие нельзя отменить!"
    )
  ) {
    return;
  }

  try {
    const response = await fetch("/words", {
      method: "DELETE",
    });

    const data = await response.json();

    if (response.ok) {
      showMessage(data.message, "success");
      document.getElementById("words-list").innerHTML = "";
    } else {
      showMessage(data.detail || "Ошибка при удалении слов", "error");
    }
  } catch (error) {
    showMessage("Ошибка при удалении слов: " + error.message, "error");
  }
}

// Загрузить статистику
async function loadStats() {
  try {
    const response = await fetch("/study_stats");
    const stats = await response.json();

    const statsDisplay = document.getElementById("stats-display");
    statsDisplay.innerHTML = `
            <div class="stat-card">
                <h3>${stats.total_words}</h3>
                <p>Всего слов</p>
            </div>
            <div class="stat-card">
                <h3>${stats.due_words}</h3>
                <p>Для повторения сегодня</p>
            </div>
            <div class="stat-card">
                <h3>${stats.learned_words}</h3>
                <p>Выученных слов</p>
            </div>
            <div class="stat-card">
                <h3>${stats.average_reviews}</h3>
                <p>Среднее повторений</p>
            </div>
        `;
  } catch (error) {
    showMessage("Ошибка при загрузке статистики: " + error.message, "error");
  }
}

// Обработчики событий
document.addEventListener("DOMContentLoaded", function () {
  // Обработчик Enter в поле URL
  document
    .getElementById("url-input")
    .addEventListener("keypress", function (e) {
      if (e.key === "Enter") {
        processUrl();
      }
    });

  // Загрузить статистику при первом заходе
  loadStats();
});

// Глобальные функции для навигации
window.showSection = showSection;
window.processUrl = processUrl;
window.getNextWord = getNextWord;
window.showTranslation = showTranslation;
window.answerWord = answerWord;
window.loadWords = loadWords;
window.clearWords = clearWords;
window.loadStats = loadStats;
