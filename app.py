import streamlit as st
import os
import datetime
from dotenv import load_dotenv

from src.helper import download_embeddings 
from src.prompt import system_prompt
from langchain_pinecone import PineconeVectorStore
from langchain_ollama import ChatOllama 
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

#page design
st.markdown(
    """
    <style>
    .stApp {
        background-color: #FFD1DC;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# 1. Page Config & UI
st.set_page_config(page_title="Medical Chatbot", page_icon="🏥")
st.title("🏥 Medical Assistant (Pierre)")

# 2. Environment & State Setup
load_dotenv()
os.environ["PINECONE_API_KEY"] = os.getenv('PINECONE_API_KEY')

# Initialize Session State for Chat History
if "chat_history" not in st.session_state:
    st.session_state.chat_history = ChatMessageHistory()

if "messages" not in st.session_state:
    st.session_state.messages = [] # For UI display

# 3. Component Initialization (Cached)
@st.cache_resource
def get_rag_chain():
    embeddings = download_embeddings()
    docsearch = PineconeVectorStore.from_existing_index(
        index_name="medical-chatbot", 
        embedding=embeddings
    )
    retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 6})

    chat_model = ChatOllama(
        model="gpt-oss:120b",
        base_url="https://ollama.com",
        headers={'Authorization': f'Bearer {os.getenv("OLLAMA_API_KEY")}'},
        streaming=True 
    )

    # Question Re-writer (Contextualizer)
    contextualize_prompt = ChatPromptTemplate.from_messages([
        ("system", "Gegeven de chatgeschiedenis en de laatste gebruikersvraag, "
                   "formuleer een zelfstandige zoekopdracht. Geef ENKEL de tekst van de zoekopdracht terug."),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    question_generator = contextualize_prompt | chat_model | StrOutputParser()

    # Formatter
    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    # Branched Retriever Logic
    def branched_retriever(inputs):
        # Accessing history from the input dictionary provided by RunnableWithMessageHistory
        if inputs.get("chat_history") and len(inputs["chat_history"]) > 0:
            optimized_query = question_generator.invoke(inputs)
            return retriever.invoke(optimized_query)
        return retriever.invoke(inputs["input"])

    # Pierre Prompt
    pierre_prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])

    # Core RAG Chain
    rag_chain = (
        {
            "context": RunnableLambda(branched_retriever) | RunnableLambda(format_docs),
            "input": lambda x: x["input"],
            "chat_history": lambda x: x["chat_history"]
        }
        | pierre_prompt 
        | chat_model 
        | StrOutputParser()
    )

    # Wrapper for History
    return RunnableWithMessageHistory(
        rag_chain,
        lambda session_id: st.session_state.chat_history, # Connects to Streamlit State
        input_messages_key="input",
        history_messages_key="chat_history",
    ), retriever

with_message_history, retriever = get_rag_chain()

def log_interaction(question, answer):
    try:
        with open("chat_logs.txt", "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"--- {timestamp} ---\nPatiënt: {question}\nPierre: {answer}\n{'-'*50}\n\n")
    except Exception as e:
        st.error(f"Log error: {e}")

# 4. Chat UI Logic
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)

if prompt := st.chat_input("Hoe kan ik u vandaag helpen?"):
    # Display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate Assistant Response
    with st.chat_message("assistant"):
        # 1. Fetch sources first for the logic check
        docs = retriever.invoke(prompt)
        sources = list(set([os.path.basename(doc.metadata.get('source', 'Onbekende bron')) for doc in docs]))
        source_text = "\n\n**Bronnen:** " + ", ".join(sources)

        # 2. Stream the response
        response_placeholder = st.empty()
        full_response = ""
        
        # Generator function for st.write_stream
        def stream_gen():
            for chunk in with_message_history.stream(
                {"input": prompt},
                config={"configurable": {"session_id": "unused"}} # ID is managed via session_state
            ):
                yield chunk

        full_response = st.write_stream(stream_gen())

        # 3. Handle the "I don't know" logic and append sources
        if "ik weet het antwoord niet" not in full_response.lower():
            st.markdown(source_text)
            full_response += source_text
        
        # 4. Log and Save
        log_interaction(prompt, full_response)
        st.session_state.messages.append({"role": "assistant", "content": full_response})

