import webbrowser

def open_youtube():
    webbrowser.open("https://www.youtube.com")
    return "Opening YouTube."

def open_google():
    webbrowser.open("https://www.google.com")
    return "Opening Google."

def search_google(query):
    if not query:
        return "What should I search for?"
    url = f"https://www.google.com/search?q={query}"
    webbrowser.open(url)
    return f"Searching Google for {query}."
