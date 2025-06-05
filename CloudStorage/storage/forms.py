from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Group
from .models import UploadedFiles
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Field


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]    
        

class LoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput())
    

class UploadedFilesForm(forms.ModelForm):
    share_mode = forms.ChoiceField(
        choices=[("users", "Users"), ("groups", "Groups")],
        widget=forms.RadioSelect,
        required=False,
        label="Share with"
    )

    class Meta:
        model = UploadedFiles
        fields = ['file_description', 'shared_users', 'shared_groups']
        
        widgets = {
            # Bootstrap form-control class
            'shared_users': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'shared_groups': forms.SelectMultiple(attrs={'class': 'form-control'}),

        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['shared_users'].queryset = User.objects.all()
        self.fields['shared_groups'].queryset = Group.objects.all()

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False  # You handle the form tag in the template
        self.helper.layout = Layout(
            Field('file_description', attrs={'autocomplete': 'off'}),
            Field('share_mode'),
            Field('shared_users', css_id='shared_users_field'),
            Field('shared_groups', css_id='shared_groups_field'),
        )