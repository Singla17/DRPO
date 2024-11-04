from typing import Union, Optional, List
from base_model import Model
from vllm_model import VLLMModel
from openai_model import OpenAIChatModel
from sentence_transformers import SentenceTransformer, util
import json
import os
import pickle

class AutoModel(Model):
 
    def __init__(
        self,
        model_name: str,
        num_gpus: int = 1,
        cuda_visible_devices: str = "0",
        dtype: str = 'bfloat16',
        gpu_memory_utilization: float = 0.98,
        max_model_len: Optional[int] = None,
        timeout: int = 600,
        open_ai_model: bool = False,
        **kwargs
    ):
        os.environ["CUDA_VISIBLE_DEVICES"] = cuda_visible_devices
        
        # Load model mappings and ICL examples
        self.model_mapping = self._load_json("./data/model_mapping.json")
        self.icl_examples = self._load_json('./data/ICL_examples.json')
        
        # Initialize embedding model for ICL retrieval
        self.embedding_model = SentenceTransformer("all-mpnet-base-v2")
        self.icl_query_embeddings = self._compute_icl_query_embeddings()            
        
        # Set up model based on configuration
        self.open_ai_model = open_ai_model
        self.model = (
            OpenAIChatModel(model_name, timeout)
            if self.open_ai_model else
            VLLMModel(model_name, num_gpus, dtype, gpu_memory_utilization, max_model_len, **kwargs)
        )

        # Load Optimized propmpt for the model if it exists
        self.optimized_prompt = self._load_optimized_prompt()
    
    def _load_json(self, file_path: str) -> dict:
        """
        Helper to load json.
        """
        with open(file_path, 'r') as f:
            return json.load(f)

    def _compute_icl_query_embeddings(self) -> dict:
        """
        Compute the embeddings of ICl queries.
        """
        icl_query_embeddings = {}
        for query in self.icl_examples:
            icl_query_embeddings[query] = self.embedding_model.encode(query)
        return icl_query_embeddings
    
    def _get_top_k_icl_examples(self, query: str, k: int) -> List[tuple]:
        """
        Retrieve the top-k in-context learning examples most similar to the provided query.
        """
        query_embedding = self.embedding_model.encode(query)
        icl_sims = [
            (util.cos_sim(self.icl_query_embeddings[icl_query], query_embedding), icl_query)
            for icl_query in self.icl_query_embeddings
        ]
        icl_sims.sort(reverse=True, key=lambda x: x[0]) 
        return icl_sims[:k]
    
    def _load_optimized_prompt(self) -> str:
        """
        This function loads the optimized prompt (if it exists) for the model
        """
        if self.model.model_name not in self.model_mapping:
            print(f"We currently do not have optimized prompt for: {self.model.model_name}.")
            return "You are a helpful assistant"
        
        prompt_path = self.model_mapping(self.model.model_name)

        with open(prompt_path, 'rb') as f:
            prompt_file =pickle.load(f)

        try:
            model_prompt = prompt_file.terminal_node.state[-1].system_prompt
        except:
            model_prompt = prompt_file

        return model_prompt

    def _prepare_system_prompt(self, optimized_prompt: bool, optimized_icl: bool, num_optimized_icl: int, user_query: str) -> str:
        """
        Prepare a system prompt for models based on optimization settings.
        """
        if optimized_prompt:
            prompt = self.optimized_prompt
        else:
            prompt = "You are a helpful assistant" 

        if optimized_icl: 
            top_icl_queries =  self._get_top_k_icl_examples(user_query, num_optimized_icl)
            for _, icl_query in top_icl_queries:
                prompt += '\n\n#Query:\n' + icl_query + '\n\n#Answer:\n' + self.icl_examples[icl_query]

        return prompt
    
    def _prepare_chat_llm_prompt(self, system_prompt: str, user_prompt: str) -> str:
        """
        Prepares the prompt in the chat template for chat LLMs.
        """
        messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
        ]
        prompt = self.model.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
        )
         
        return prompt

    def generate(
        self,
        user_query: str,
        optimized_prompt: bool = True,
        optimized_icl: bool = True,
        num_optimized_icl: int = 3,
        temperature: float = 0.7,
        top_p: float = 0.95,
        max_new_tokens: int = 512,
        stop: Optional[Union[str, List[str]]] = None,
        **kwargs
    ) -> str:
        """
        Generate a response from the model based on the user prompt and provided parameters.
        
        Args:
            user_query (str): The prompt provided by the user.
            optimized_prompt (bool): Whether to use optimized prompts.
            optimized_icl (bool): Whether to use optimized in-context learning.
            temperature (float): Sampling temperature for generation.
            top_p (float): Cumulative probability for nucleus sampling.
            max_new_tokens (int): Maximum number of tokens to generate.
            stop (Optional[Union[str, List[str]]]): Sequence(s) at which to stop generation.
            **kwargs: Additional parameters for the generation function.
        
        Returns:
            str: Generated text from the model.
        """

        if optimized_icl:
            assert num_optimized_icl > 0, "Number of ICL examples should be > 0"

        # Prepare system prompt
        system_prompt = self._prepare_system_prompt(optimized_prompt, optimized_icl, num_optimized_icl, user_query)

        # Prepare user prompt
        user_prompt = f"# Query:\n{user_query}\n\n# Answer:\n<START>"
        
        # Generate response based on model type
        if self.open_ai_model:
            return self.model.generate(
                user_prompt, system_prompt, None, temperature, top_p, max_new_tokens, stop, num_return_sequences=1,
                stream=False, **kwargs
            )
        else:
            if self.model.tokenizer.chat_tempalte is not None:
                prompt = self._prepare_chat_llm_prompt(system_prompt, user_prompt)
            else:
                prompt = system_prompt + "\n\n" + user_prompt

            return self.model.generate(prompt, temperature, top_p, max_new_tokens, stop, **kwargs)
    

