from django.shortcuts import render

def chat_index(request):
    return render(request, 'index.html')

def room(request, room_name):
    return render(request, 'room.html', {
        'room_name': room_name
    })
