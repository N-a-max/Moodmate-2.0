document.addEventListener('DOMContentLoaded', () => {
    const moodForm = document.getElementById('mood-form');
    const moodText = document.getElementById('mood-text');
    const resultContainer = document.getElementById('result-container');
    const detectedEmotion = document.getElementById('detected-emotion');
    const recommendedQuote = document.getElementById('recommended-quote');
    const submitButton = moodForm.querySelector('button');
    const buttonText = submitButton.querySelector('.button-text');
    const spinner = submitButton.querySelector('.spinner');

    // New elements for music
    const musicContainer = document.getElementById('music-container');
    const musicList = document.getElementById('music-list');

    moodForm.addEventListener('submit', (event) => {
        event.preventDefault();

        buttonText.classList.add('hidden');
        spinner.classList.remove('hidden');
        submitButton.disabled = true;
        musicContainer.classList.add('hidden'); // Hide old results
        musicList.innerHTML = ''; // Clear old results

        const text = moodText.value;

        // First, get the emotion and quote
        fetch('/predict', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) { throw new Error(data.error); }

            detectedEmotion.textContent = data.detected_emotion;
            recommendedQuote.textContent = data.recommended_quote;
            resultContainer.classList.remove('hidden');
            setTimeout(() => { resultContainer.classList.add('visible'); }, 10);
            
            // Now, use the detected emotion to get music recommendations
            return fetch('/recommend', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ emotion: data.detected_emotion }),
            });
        })
        .then(response => response.json())
        .then(tracks => {
            if (tracks.error) { throw new Error(tracks.error); }
            
            tracks.forEach(track => {
                const trackElement = document.createElement('a');
                trackElement.href = track.url;
                trackElement.target = '_blank'; // Open in new tab
                trackElement.className = 'track';
                
                trackElement.innerHTML = `
                    <img src="${track.album_art}" alt="Album art for ${track.name}">
                    <div class="track-info">
                        <div class="track-name">${track.name}</div>
                        <div class="track-artist">${track.artist}</div>
                    </div>
                `;
                musicList.appendChild(trackElement);
            });
            musicContainer.classList.remove('hidden');
        })
        .catch((error) => {
            console.error('Error:', error);
            if (error.message.includes("User not logged in")) {
                alert("Please log in with Spotify to get music recommendations.");
            } else {
                alert("Sorry, an error occurred. Please try again.");
            }
        })
        .finally(() => {
            buttonText.classList.remove('hidden');
            spinner.classList.add('hidden');
            submitButton.disabled = false;
        });
    });
});