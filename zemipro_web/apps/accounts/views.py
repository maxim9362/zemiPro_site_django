from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from .forms import ClientProfileForm, RegistrationForm, WorkerProfileForm
from .services import (
    create_or_update_client_profile, get_client_profile,
    create_or_update_worker_profile, get_worker_profile,
)


def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('accounts:client_profile')
    else:
        form = RegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def client_profile_view(request):
    profile = get_client_profile(request.user)

    if request.method == 'POST':
        form = ClientProfileForm(request.POST, instance=profile)
        if form.is_valid():
            create_or_update_client_profile(request.user, form.cleaned_data)
            messages.success(request, 'Профиль клиента сохранён.')
            return redirect('marketplace:client_dashboard')
    else:
        initial = {}
        if profile:
            initial = {
                'city': profile.city,
                'contact': profile.contact,
            }
        form = ClientProfileForm(initial=initial)

    return render(request, 'accounts/client_profile.html', {'form': form, 'profile': profile})


@login_required
def worker_profile_view(request):
    profile = get_worker_profile(request.user)

    if request.method == 'POST':
        form = WorkerProfileForm(request.POST, instance=profile)
        if form.is_valid():
            create_or_update_worker_profile(request.user, form.cleaned_data)
            messages.success(request, 'Профиль мастера сохранён.')
            return redirect('marketplace:worker_dashboard')
    else:
        initial = {}
        if profile:
            initial = {
                'city': profile.city,
                'contact': profile.contact,
                'description': profile.description,
                'skills': profile.skills.all(),
                'receive_notifications': profile.receive_notifications,
            }
        form = WorkerProfileForm(initial=initial)

    return render(request, 'accounts/worker_profile.html', {'form': form, 'profile': profile})
