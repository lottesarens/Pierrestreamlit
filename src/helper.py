#from langchain.document_loaders import PyPDFLoader, DirectoryLoader
#from langchain.text_splitter import RecursiveCharacterTextSplitter 
#from langchain.embeddings import HuggingFaceBgeEmbeddings 
#from typing import List 
#from langchain.schema import Document

import os

# Extract text from pdf files
# PyPDFLoader used to specifically load PDF and data is the place where you store the PDF 
# from langchain.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader

# from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_text_splitters import RecursiveCharacterTextSplitter


def load_pdf_files(data):
    loader = DirectoryLoader(data, glob="*.pdf", loader_cls=PyPDFLoader)
    documents = loader.load()
    return documents


from typing import List

# from langchain.schema import Document
from langchain_core.documents import Document


def filter_to_minimal_docs(docs: List[Document]) -> List[Document]:
    # cleaning the data so we only get the usefull stuff
    minimal_docs: List[Document] = []
    for doc in docs:
        src = doc.metadata.get("source")
        minimal_docs.append(
            Document(page_content=doc.page_content, metadata={"source": src})
        )

    return minimal_docs


# Split the document in smaller chunks
# each chunk will have a chunk_size amount of tokens, so here each chunk has 500 tokens 
def text_split(minimal_docs):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500, chunk_overlap=20, length_function=len
    )
    texts_chunk = text_splitter.split_documents(minimal_docs)
    return texts_chunk


# HuggingFace is a free embedding model, we can use others if we want to


# In LangChain 1.x, we use the dedicated huggingface package
from langchain_huggingface import HuggingFaceEmbeddings


def download_embeddings():
    # This BGE model is a great choice for performance
    #model_name = "BAAI/bge-small-en-v1.5"
    #this should be multilangual model
    model_name = "intfloat/multilingual-e5-small"

    # In 1.x, HuggingFaceEmbeddings is the universal class for HF models
    embeddings = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},  # Force CPU if you don't have a GPU
    )
    return embeddings
