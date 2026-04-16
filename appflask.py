#HISTORY AND STREAMING ADDED IN HERE

from flask import Flask, render_template, request, Response, stream_with_context
from src.helper import download_embeddings 
from langchain_pinecone import PineconeVectorStore
from langchain_ollama import ChatOllama 
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_community.chat_message_histories import ChatMessageHistory ### NIEUW: GEHEUGEN ###
from langchain_core.runnables.history import RunnableWithMessageHistory ### NIEUW: GEHEUGEN ###
from langchain_core.runnables import RunnableLambda
from dotenv import load_dotenv
import os
import datetime
from src.prompt import system_prompt


app = Flask(__name__)
load_dotenv()

# Setup
os.environ["PINECONE_API_KEY"] = os.getenv('PINECONE_API_KEY')
embeddings = download_embeddings()
docsearch = PineconeVectorStore.from_existing_index(index_name="medical-chatbot", embedding=embeddings)
retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 6})

chatModel = ChatOllama(
    model="gpt-oss:120b",
    base_url="https://ollama.com",
    headers={'Authorization': 'Bearer ' + os.getenv('OLLAMA_API_KEY')},
    streaming=True 
)

# ### NIEUW: GEHEUGEN OPSLAG ###
store = {}

def get_session_history(session_id: str):
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

def log_interaction(question, answer):
    try:
        with open("chat_logs.txt", "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"--- {timestamp} ---\nPatiënt: {question}\nPierre: {answer}\n{'-'*50}\n\n")
    except Exception as e: print(f"Log error: {e}")

# ### AANGEPAST: PROMPT MET HISTORY PLACEHOLDER ###
prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
])

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

# --- 1. De "Herschrijver" (Vertaalt 'hiervan' naar de echte context) ---
contextualize_prompt = ChatPromptTemplate.from_messages([
    ("system", "Gegeven de chatgeschiedenis en de laatste gebruikersvraag, "
               "formuleer een zelfstandige zoekopdracht. Geef ENKEL de tekst van de zoekopdracht terug."),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])

# Dit is een klein hulp-ketentje
question_generator = contextualize_prompt | chatModel | StrOutputParser()

# --- 2. De Slimme Zoekfunctie (Retriever) ---
def branched_retriever(inputs):
    # Als er al wat gezegd is, laat Pierre de vraag verduidelijken voor de PDF-zoeker
    if inputs.get("chat_history") and len(inputs["chat_history"]) > 0:
        optimized_query = question_generator.invoke(inputs)
        return retriever.invoke(optimized_query)
    # Eerste vraag? Zoek gewoon direct
    return retriever.invoke(inputs["input"])

# --- 3. De Hoofd Chain (De 'Pierre' die de patiënt ziet) ---
# Dit is wat ik 'qa_prompt' noemde:
pierre_prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt), # Jouw tekst uit src/prompt.py
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])

# --- 3. De Hoofd Chain ---
rag_chain = (
    {
        # Gebruik RunnableLambda om de functies compatibel te maken met de | operator
        "context": RunnableLambda(branched_retriever) | RunnableLambda(format_docs),
        "input": lambda x: x["input"],
        "chat_history": lambda x: x["chat_history"]
    }
    | pierre_prompt 
    | chatModel 
    | StrOutputParser()
)

# --- 4. De finale wrapper die alles onthoudt ---
with_message_history = RunnableWithMessageHistory(
    rag_chain,
    get_session_history,
    input_messages_key="input",
    history_messages_key="chat_history",
)

@app.route("/")
def home(): return render_template("home.html")

@app.route("/chat")
def index(): return render_template("chat.html")

@app.route("/get", methods=["GET", "POST"])
def chat():
    msg = request.form["msg"]
    if not msg: return ""

    # Bronnen ophalen
    docs = retriever.invoke(msg)
    sources = list(set([os.path.basename(doc.metadata.get('source', 'Onbekende bron')) for doc in docs]))
    source_text = "\n\n<br><strong>Bronnen:</strong> " + ", ".join(sources)

    def generate():
        full_response = ""
        # Pierre begint te streamen
        for chunk in with_message_history.stream(
            {"input": msg},
            config={"configurable": {"session_id": "temp_user"}}
        ):
            full_response += chunk
            yield chunk
        
        # --- DE FIX ---
        # We checken of de standaard "weet het niet" zin in het antwoord zit.
        # Let op: zorg dat deze zin EXACT matcht met wat in je src/prompt.py staat.
        if "ik weet het antwoord niet" not in full_response.lower():
            # Alleen als hij het wel weet, sturen we de bronnen mee
            yield source_text
            full_response += source_text
        # --- EINDE FIX ---
        
        log_interaction(msg, full_response)

    return Response(stream_with_context(generate()), mimetype='text/plain')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)