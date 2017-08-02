def check_commands(message):
    if message == "/help":
        return "*Help Menu*\n/help - For a list of commands\n/about - About page"
    elif message == "/about":
        return "*About Page*\nThank you for using SingBusBot. \nPlease do check out the code at https://github.com/errorfourten/singbusbot and new ideas are always welcome."
    elif message == "/start":
        return "Welcome to Singapore Bus Bot! Just enter a bus stop code and find the next bus. For example, try entering 53009 or Bishan Int. /help for more information"
    else:
        return False
