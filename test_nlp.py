from transformers import pipeline

# Initialize the model once and reuse it
emotion_classifier = pipeline(
    "text-classification", 
    model="j-hartmann/emotion-english-distilroberta-base"
)

def detect_emotion(text):
    
    result = emotion_classifier(text)
    top_emotion = result[0]['label']
    return top_emotion