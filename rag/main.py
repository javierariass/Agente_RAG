from ollama_chat import send_to_rag

if __name__ == "__main__":
    message = input('Pregunta algo: \n')
    print(send_to_rag(message))
    