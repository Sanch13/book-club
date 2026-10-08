from django import forms

from .models import Review, ReviewComment


class ReviewCommentForm(forms.ModelForm):
    class Meta:
        model = ReviewComment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Напишите комментарий к отзыву...',
                'class': 'w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#A2D813]'
            })
        }
        labels = {
            'text': ''
        }


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Напишите ваш отзыв о книге...',
                'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#A2D813]'
            })
        }
        labels = {
            'text': ''
        }
