from llm_model import llm_model
from embeddings import chroma_vectorstore
from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate
from typing import TypedDict, Annotated
from langchain_core.runnables import RunnablePassthrough, RunnableMap, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall

# .env 파일에서 환경 변수 로드
load_dotenv()

# LLM Load
llm = llm_model()

# 그래프 상태를 정의하는 클래스
class MyState(TypedDict):
    question: Annotated[str, "question"]        # 질문
    context: Annotated[str, "context"]          # 문서의 검색 결과
    answer: Annotated[str, "answer"]            # 답변
    relevance: Annotated[str, "relevance"]      # 관련성

# Retiever
vectorstore = chroma_vectorstore()
retriever = vectorstore.as_retriever(
    search_type="similarity",
    search_kwargs={"k": 10}
)

# Retiever Node -> context
def retrieve_node(state: MyState) -> MyState:
    """
    주어진 질문을 기반으로 문서를 검색하여 상태의 'context'를 업데이트합니다.
    """
    question = state["question"]
    documents = retriever.invoke(question)
    context = "\n\n".join([doc.page_content for doc in documents])

    return {"context": context}

# LLM Answer Node -> evlauate
def answer_node(state: MyState) -> MyState:
    """
    주어진 Context를 기반으로 질문에 기반한 답변을 생성하여 상태의 'answer'를 업데이트합니다.
    """
    question = state["question"]
    context = state["context"]

    # Prompt Template Define
    prompt_template = PromptTemplate.from_template([
        ("system", "당신은 게임 개발조직의 유용한 AI Assitant입니다. 다음 참조 문서와 질문을 바탕으로 답변을 제공하세요. 답변은 참조 문서의 정보에만 근거해야 하며, 모르는 내용은 '모르는 내용입니다'라고 답변하세요. 사용자에게 필요한 정보를 명확하고 간결하게 전달해 주세요."),
        ("user", "참조 문서: \n{context}\n\n질문: {question}")
    ])

    # RAG Chain Composition
    rag_chain = (
        RunnableMap({
            "question": RunnablePassthrough(),
            "context": RunnablePassthrough()
        })
        | prompt_template
        | llm
        | StrOutputParser()
    )
    answer = rag_chain.invoke({"question": question, "context": context})
    
    return {"answer": answer}

# Evaluate Node
def relevance_node(answer):
    """
    생성된 context가 질문에 맞는 문장인지 확인하는 함수입니다.
    """
    dataset = answer
    result = evaluate(
    dataset=dataset,
    metrics=[
        context_precision,
        context_recall,
        answer_relevancy,
        faithfulness
    ]
)
    return result

# StateGraph 인스턴스 생성
graph = StateGraph(MyState)

# Node Define
graph.add_node("retirever", retrieve_node)
graph.add_node("answer", answer_node)
graph.add_node("relevance", relevance_node)

# Edge Define
graph.add_edge(START, "retriever")          # Set Entry Point
graph.add_edge("retriever", "answer")       # 질문 검색 -> 답변
graph.add_edge("answer", "relevance")       # 질문 검색 -> 답변
graph.add_edge("relevance", END)               # 답변 -> 종료

# Compile
app = graph.compile()

# Response
if __name__ == "__main__":
    response = app.invoke({"question": "각 캐릭터의 특징을 알려줘"})
    print(response)