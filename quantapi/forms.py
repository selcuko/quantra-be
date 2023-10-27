from django import forms
from quantapi.models import Session

class SessionInitForm(forms.ModelForm):
    class Meta:
        model = Session
        fields = ['session_type', 'freq', 'strategy_name', 'strategy_parameters', 'planned_shutdown', 'symbol']
        
    
    def is_valid(self) -> bool:
        return super().is_valid()
