from django.http import HttpResponse


def home(request):
    return HttpResponse("<h1>Shared Household Chores</h1>")
