import discord
from discord.ext import commands
import feedparser
import configparser
import os
import time
import json
import threading


#credential parsing from credentials.ini
parser = configparser.ConfigParser()
parser.read('credentials.ini')
token = parser['Login']['Token']

mangaList = {}
mangaDB = {}

#initializing data
if not os.path.exists("data"):
    print("No data directory found. Creating directory...")
    os.makedirs("data")

if os.path.isfile('data/subLists.json'):
    listFile = open('data/subLists.json')
    mangaList = json.load(listFile, parse_int=True)
    listFile.close()


description = 'A bot that allows users to subscribe to updates to manga from mangadex.org'
bot = commands.Bot(command_prefix='$', description=description)

@bot.event
async def on_ready():
    print('Connected!')
    update_thread = threading.Thread(target=checkFeeds)

#Adds user to a subscription list
@bot.command(pass_context=True)
async def subscribe(ctx, mangaId: int):
    """Adds user to the subscription list for the manga specified by ID"""

    #check if allowed to send messages in this channel
    if not ctx.message.channel.permissions_for(ctx.message.guild.me).send_messages:
        return

    if not mangaId in mangaList:

        #check if id is valid
        response = feedparser.parse('https://mangadex.org/rss/manga_id/' + str(mangaId))
        if len(response.entries) == 0:
            await ctx.message.channel.send("Manga does not exist.")
            return

        else:
            #create sub list for the manga and add user to it
            mangaList[mangaId] = {}
            mangaList[mangaId][ctx.message.channel.id] = []
            mangaList[mangaId][ctx.message.channel.id].append(ctx.message.author.id)
            
            #create db of known chapters for the manga
            mangaDB[mangaId] = []
            for filteredEntry in (rawEntries for rawEntries in response.entries if "Language: English" in rawEntries.description):
                mangaDB[mangaId].append(filteredEntry.title)
                write_db_changes()

    else:

        if not ctx.message.channel.id in mangaList[mangaId]:
            mangaList[mangaId][ctx.message.channel.id] = []
            mangaList[mangaId][ctx.message.channel.id].append(ctx.message.author.id)

        else:

            if ctx.message.author.id in mangaList[mangaId][ctx.message.channel.id]:
                await ctx.message.channel.send("You're already subscribed to this manga!")
                return

            else:
                mangaList[mangaId][ctx.message.channel.id].append(ctx.message.author.id)

    #save changes to disk
    write_sub_changes()
    await ctx.message.channel.send('Successfully subscribed!')
    return

#Removes user from a subscription list
@bot.command(pass_context=True)
async def unsubscribe(ctx, mangaId: int):
    """Removes user from a subscription list"""
    if not mangaId in mangaList:
        await ctx.message.channel.send("A list for this manga does not exist.")
        return
    if not ctx.message.channel.id in mangaList[mangaId]:
        await ctx.message.channel.send("You do not have a subscription for this manga in this channel.")
        return
    if not ctx.message.author.id in mangaList[mangaId][ctx.message.channel.id]:
        await ctx.message.channel.send("You do not have a subscription for this manga in this channel.")
        return
    mangaList[mangaId][ctx.message.channel.id].remove(ctx.message.author.id)
    if not mangaList[mangaId][ctx.message.channel.id]:
        mangaList[mangaId].pop(ctx.message.channel.id)
        if not mangaList[mangaId]:
            mangaList.pop(mangaId)
    write_sub_changes()
    await ctx.message.channel.send("Successfully unsubscribed!")
    return

@bot.command(pass_context=True)
async def shutdown(ctx):
    await bot.logout()

def write_sub_changes():
    writeFile = open('data/subLists.json', mode='w')
    json.dump(mangaList, writeFile)
    writeFile.close()

def write_db_changes():
    writeFile = open('data/mangaDB.json', mode='w')
    json.dump(mangaDB, writeFile)
    writeFile.close()

def checkFeeds():
    while True:
        for manga, channels in mangaList:
            response = feedparser.parse('https://mangadex.org/rss/manga_id/' + str(manga))
	    if status != 200:
                continue
            newEntries = []
            for filteredEntry in (rawEntries for rawEntries in response.entries if "Language: English" in rawEntries.description):
                if not filteredEntry.title in mangaDB[manga]:
                    newEntries.append(filteredEntry)
            if len(newEntries) > 0:
                mangaDB[manga].extend(newEntries)
                write_db_changes()
                bot.loop.run_until_complete(notifySubs(manga, channels, newEntries))
            time.sleep(2)
        time.sleep(1800)

   

async def notifySubs(mangaId: int, chList: list, entries: list):
    for channel, users in chList:
        channelObj = bot.get_channel(channel)
        guild = channelObj.guild
        memberPings = ""
        descriptionString = ""
        for user in users:
            memberPings += " " + guild.get_member(user).mention
        for entry in entries:
            descriptionString += '[' + entry.title + '](' + entry.link + ')\n'
        sendEmbed = discord.Embed(title='New Chapters',
                                  description=descriptionString)
        await channelObj.send(content=memberPings, embed=sendEmbed)
    return

@bot.command()
async def invite_link():
    bot.say('https://discordapp.com/oauth2/authorize?client_id=473271749027561473&scope=bot')

bot.run(token)




