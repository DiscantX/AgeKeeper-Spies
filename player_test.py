import lobby

profileid = 10056062

def player(event):
    print(event)

def main():
    subscriptions = lobby.subscribe(["players"], player_ids = [profileid])
    lobby.connect_to_subscriptions(subscriptions, player)
    
if __name__ == "__main__":
    main()