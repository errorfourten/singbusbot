def check_commands(message):
    if message == "/help":
        return "*Help Menu*\n/help - For a list of commands\n/about - About page"
    elif message == "/about":
        return "*About Page*\nThank you for using SingBusBot. Please do check out the code at https://github.com/errorfourten/singbusbot and suggest new ideas you may have."
    else:
        return False
