import streamlit as st
import os
import nest_asyncio
import asyncio
import logging
from dotenv import load_dotenv
from llama_index.core import (
    SimpleDirectoryReader,
    VectorStoreIndex,
    SummaryIndex,
    Settings
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.core.tools import QueryEngineTool
from llama_index.core.query_engine.router_query_engine import RouterQueryEngine
from llama_index.core.selectors import LLMSingleSelector
from llama_index.core.agent.workflow import AgentWorkflow
import google.generativeai as genai

# Setup logging
logging.basicConfig(
    filename="chatbot_logs.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

nest_asyncio.apply()

# Load environment variables from .env file
load_dotenv()
# 1. API Key setup
# Read the key from environment
api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

st.set_page_config(page_title="📄 Floyd Doc Chatbot", layout="centered")
st.title("🤖 Chat with Floyd Project Documentation")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# File uploader
uploaded_file = st.file_uploader("📤 Upload your `.md` or `.txt` documentation file", type=["md", "txt"])

if uploaded_file and "query_engine_agent" not in st.session_state:
    with open("temp_doc.md", "wb") as f:
        f.write(uploaded_file.read())

    st.success("✅ Document uploaded successfully!")

    # 2. Load and process
    reader = SimpleDirectoryReader(input_files=["temp_doc.md"])
    documents = reader.load_data()
    splitter = SentenceSplitter(chunk_size=1024)
    nodes = splitter.get_nodes_from_documents(documents)

    # 3. LLM and Embeddings setup
    Settings.llm = GoogleGenAI(model="models/gemini-1.5-flash")
    Settings.embed_model = GoogleGenAIEmbedding(model_name="models/embedding-001")

    # 4. Build indexes
    summary_index = SummaryIndex(nodes)
    vector_index = VectorStoreIndex(nodes)

    summary_query_engine = summary_index.as_query_engine(
        response_mode="tree_summarize", use_async=True
    )
    vector_query_engine = vector_index.as_query_engine()

    summary_tool = QueryEngineTool.from_defaults(
        name="summary_tool",
        query_engine=summary_query_engine,
        description="Useful for summarization questions related to Floyd_customer123_4b34af6c-6f7e-4526-b305-2454a93012ee_documentation_md_files_README_AI.md file."
    )

    vector_tool = QueryEngineTool.from_defaults(
        name="vector_tool",
        query_engine=vector_query_engine,
        description="Useful for retrieving specific context from the Floyd_customer123_4b34af6c-6f7e-4526-b305-2454a93012ee_documentation_md_files_README_AI.md file."
    )

    router_query_engine = RouterQueryEngine(
        selector=LLMSingleSelector.from_defaults(),
        query_engine_tools=[summary_tool, vector_tool],
        verbose=True,
    )

    query_engine_tool = QueryEngineTool.from_defaults(
    query_engine=router_query_engine,
    name="floyd_doc_summary_or_vector_report",
    description=(
        "Answers questions based on the Floyd_customer123_4b34af6c-6f7e-4526-b305-2454a93012ee_documentation_md_files_README_AI.md file "
        "by routing them to either a summarization engine or a vector-based retrieval engine."
    ),
    return_direct=True
)

    system_prompt = """
    You are an assistant that can answer questions about a project based on its documentation.

    Use the tool floyd_doc_summary_or_vector_report to answer any user query related to:
    - system overview, design, or architecture (summary queries)
    - code-level, file-specific, or dependency setup (vector/detail queries)

    Do not attempt to answer on your own. Always use the tool.
    """

    query_engine_agent = AgentWorkflow.from_tools_or_functions(
        tools_or_functions=[query_engine_tool],
        llm=Settings.llm,
        system_prompt=system_prompt,
    )
    st.session_state.query_engine_agent = query_engine_agent

# Handle user input and chat flow
if "query_engine_agent" in st.session_state:
    user_input = st.chat_input("Ask a question about the document...")

    if user_input:
        # Display full chat history before processing new input
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Show user message
        st.chat_message("user").markdown(user_input)
        st.session_state.messages.append({"role": "user", "content": user_input})
        logging.info(f"User: {user_input}")

        try:
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    async def get_response(query):
                        return await st.session_state.query_engine_agent.run(query)

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    response = loop.run_until_complete(get_response(user_input))
                    loop.close()

                    response_text = str(response)
                    st.markdown(response_text)
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    logging.info(f"Agent: {response_text}")

        except Exception as e:
            st.error("Something went wrong.")
            logging.error(f"Error: {str(e)}")

    