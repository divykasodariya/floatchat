from transformers import BertForSequenceClassification, BertTokenizer
import torch

MODEL_PATH = r"intent_classifi\floatchat_intent_model"
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

tokenizer = BertTokenizer.from_pretrained(MODEL_PATH)
model = BertForSequenceClassification.from_pretrained(MODEL_PATH)
model.to(device)
print(next(model.parameters()).device)
model.eval()

labels = ['Database Query', 'General Information', 'Out of Scope']

def classify_intent(text):
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        outputs = model(**inputs)
    pred = torch.argmax(outputs.logits, dim=1).item()
    return {
        "predicted_class": pred,
        "predicted_label": labels[pred]
    }

