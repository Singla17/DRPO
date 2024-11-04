from base_model import Model
from typing import Optional, List
import openai
import os

class OpenAIChatModel(Model):
    def __init__(self, 
                 model_name: str = 'gpt-3.5-turbo',
                 timeout = 600
    ):
        self.model_name = model_name
        
        API_KEY = os.getenv("OPENAI_API_KEY", None)
        if API_KEY is None:
            raise ValueError("OPENAI_API_KEY not set, please run `export OPENAI_API_KEY=<your key>` to set it")
        else:
            openai.api_key = API_KEY
        
        
        self.client = openai.OpenAI(
            timeout=timeout,
        )
    
    @staticmethod
    def load():
        pass

    def generate(self, 
                 user_prompt: Optional[str] = None,
                 system_prompt: Optional[str] = None,
                 messages: Optional[List[dict]] = None,
                 temperature: float = 0,
                 top_p: float = 1,  
                 max_new_tokens: int = 512,
                 stop: Optional[str] = None,
                 num_return_sequences: int = 1,
                 json_output: bool = False,
                 **kwargs
    ) -> str:
        
        # assert, either give both system_prompt and user_prompt or give messages
        assert user_prompt is not None or messages is not None, \
            "Either give both system_prompt and user_prompt or give messages"
            
        if messages is None:
            # assert, user prompt is not None
            assert user_prompt is not None, "user_prompt is required if you do not pass messages"
            
            if system_prompt is not None:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            
            else:
                messages = [
                    {"role": "user", "content": user_prompt}
                ]
        
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_new_tokens,
            top_p=top_p,
            n=num_return_sequences,
            stop=stop,
            response_format={ "type": "json_object" } if json_output else None,
            seed=0,
            **kwargs
        )

        if num_return_sequences == 1:
            return response.choices[0].message.content
        else:
            return [choice.message.content for choice in response.choices]