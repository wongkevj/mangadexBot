import discord
from discord.ext import commands
import feedparser
import configparser
import aiohttp
import os
import time
import json
import threading
import datetime
import lxml.html
import asyncio
from sys import exit


#credential parsing from credentials.ini
parser = configparser.ConfigParser()
parser.read('credentials.ini')
token = parser['Login']['Token']
owner = parser['Owner']['ID']

"""
mangaList (dict):
The data structure containing the subscriptions 
    keys - mangaIds (int)
    vals - channels (dict)
               keys - channel ids (int)
               vals - user ids (list of ints)
"""
mangaList = {}

"""
mangaDB (dict):
The data structure containing the known chapters
of every series subscribed to 
    keys - mangaIds (int)
    vals - chapter ids (list of ints)
"""
mangaDB = {}

"""
db for the debug function, identical to mangaDB
"""
#loremDB = []

#initializing data, read from disk if data is there
if not os.path.exists("data"):
    print("No data directory found. Creating directory...")
    os.makedirs("data")

if os.path.isfile('data/subLists.json'):
    listFile = open('data/subLists.json')
    mangaList = json.load(listFile)
    listFile.close()

if os.path.isfile('data/mangaDB.json'):
    dbFile = open('data/mangaDB.json')
    mangaDB = json.load(dbFile)
    dbFile.close()

description = 'A bot that allows users to subscribe to updates to manga from mangadex.org'
bot = commands.Bot(command_prefix='$', description=description)

#startup function
@bot.event
async def on_ready():
    print('Connected!')
    asyncio.ensure_future(checkFeeds())

#check whether a manga exists
async def valid(mangaId: int):
    #testing async with
    pageJson = {}
    async with aiohttp.ClientSession() as session:
        async with session.get('https://mangadex.org/api/manga/' + str(mangaId)) as resp:
            pageJson = await resp.json()
    return pageJson['status'] == 'OK'

#Adds user to a subscription list
@bot.command(pass_context=True)
async def subscribe(ctx, mangaId: int):
    """Adds user to the subscription list for the manga specified by ID"""

    #check if allowed to send messages in this channel
    print("in subscribe!")
    if not ctx.message.channel.permissions_for(ctx.message.guild.me).send_messages:
        return

    if not mangaId in mangaList:

        #check if id is valid
        pageJson = {}
        async with aiohttp.ClientSession() as session:
            async with session.get('https://mangadex.org/api/manga/' + str(mangaId)) as resp:
                pageJson = await resp.json()

        if pageJson.get('status') != 'OK':
            print("manga not found")
            await ctx.message.channel.send("Manga does not exist.")
            return

        else:
            #create sub list for the manga and add user to it
            mangaList[mangaId] = {}
            mangaList[mangaId][ctx.message.channel.id] = []
            mangaList[mangaId][ctx.message.channel.id].append(ctx.message.author.id)
            
            #create db of known chapters for the manga
            mangaDB[mangaId] = {}
            mangaDB[mangaId]['title'] = pageJson['manga']['title']
            mangaDB[mangaId]['chapters'] = []
            englishChaps = [chapterId for chapterId in pageJson['chapter'].keys() if pageJson['chapter'][chapterId]['lang_code'] == 'gb']
            mangaDB[mangaId]['chapters'].extend(englishChaps)
            write_db_changes()
            """
            for filteredEntry in (rawEntries for rawEntries in response.entries if "Language: English" in rawEntries.description):
                mangaDB[mangaId].d(filteredEntry.title)
                write_db_changes()
            """
    else:
        #if the channel doesn't exist, create it
        if not ctx.message.channel.id in mangaList[mangaId]:
            mangaList[mangaId][ctx.message.channel.id] = []
            mangaList[mangaId][ctx.message.channel.id].append(ctx.message.author.id)

        else:
            #check if user is already subscribed
            if ctx.message.author.id in mangaList[mangaId][ctx.message.channel.id]:
                await ctx.message.channel.send("You're already subscribed to this manga!")
                return

            else:
                #subscribe!
                mangaList[mangaId][ctx.message.channel.id].append(ctx.message.author.id)

    #save changes to disk
    write_sub_changes()
    await ctx.message.channel.send('Successfully subscribed to ' + pageJson['manga']['title'] + '!')
    return

@bot.command(pass_context=True)
async def subscriptions(ctx):
    authorId = ctx.message.author.id
    subs = []
    for manga, channels in mangaList.items():
        for channel, users in channels.items():
            if authorId in users:
                subs.append(manga)
    if subs:
        titleString = 'Current Subscriptions for ' + ctx.message.author.display_name 
        descString = ''
        for sub in subs:
            descString += '[' + str(sub) + ': ' + mangaDB[sub]['title'] + ']' + '(https://mangadex.org/manga/' + str(sub) + ')\n'
        descString += '\nFor more info about these series, use `$info [ID of the manga]`!'
        sendEmbed = discord.Embed(title=titleString, description=descString)
        sendEmbed.set_thumbnail(url=ctx.message.author.avatar_url)
    await ctx.message.channel.send(embed=sendEmbed)
        

        

#Removes user from a subscription list
@bot.command(pass_context=True)
async def unsubscribe(ctx, mangaId: int):
    """Removes user from a subscription list"""

    #not subscribed cases
    if not mangaId in mangaList:
        await ctx.message.channel.send("A list for this manga does not exist.")
        return
    if not ctx.message.channel.id in mangaList[mangaId]:
        await ctx.message.channel.send("You do not have a subscription for this manga in this channel.")
        return
    if not ctx.message.author.id in mangaList[mangaId][ctx.message.channel.id]:
        await ctx.message.channel.send("You do not have a subscription for this manga in this channel.")
        return

    #remove them from the list
    mangaList[mangaId][ctx.message.channel.id].remove(ctx.message.author.id)
    if not mangaList[mangaId][ctx.message.channel.id]:
        #if there's no one left on the channel's list, remove it
        mangaList[mangaId].pop(ctx.message.channel.id)
        if not mangaList[mangaId]:
            #if there are no more channels, remove the manga from the list
            mangaList.pop(mangaId)

    write_sub_changes()
    await ctx.message.channel.send("Successfully unsubscribed!")
    return

@bot.command(pass_context=True)
async def shutdown(ctx):
    await bot.logout()
    pendingTasks = asyncio.Task.all_tasks()
    for task in pendingTasks:
        task.cancel()
    exit()

@bot.command(pass_context=True)
async def info(ctx, mangaId: int):
    async with aiohttp.ClientSession() as session:
        async with session.get('https://mangadex.org/api/manga/' + str(mangaId)) as resp:
            if resp.status == 200:
                jsonResp = (await resp.json())
                mangaTitle = jsonResp['manga']['title']
                mangaDesc = jsonResp['manga']['description']
                mangaImg = 'https://mangadex.org' + jsonResp['manga']['cover_url']
                sendEmbed = discord.Embed(title=mangaTitle,
                                          url='https://mangadex.org/manga/' + str(mangaId), 
                                          description=mangaDesc)
                sendEmbed.set_image(url=mangaImg)
                await ctx.message.channel.send(embed=sendEmbed)
            else:
                await ctx.message.channel.send("Unable to fetch info at this time")
                print("Bad request!")
    


#utility commands to write changes to disk
#TODO - consolidate into single generic function?
def write_sub_changes():
    writeFile = open('data/subLists.json', mode='w')
    json.dump(mangaList, writeFile)
    writeFile.close()

def write_db_changes():
    writeFile = open('data/mangaDB.json', mode='w')
    json.dump(mangaDB, writeFile)
    writeFile.close()


#infinite loop which checks the RSS feeds and calls notifySubs when new updates have been found
async def checkFeeds():
    while True:

        print('[' + str(datetime.datetime.now()) + '] - Checking feeds...')


        updatesFound = False 
        for manga, channels in mangaList.items():
            
            async with aiohttp.ClientSession() as session:

                async with session.get('https://mangadex.org/api/manga/' + str(manga)) as resp:

                    if resp.status == 200:
                        pageJson = await resp.json()
                        englishChaps = [chapterId for chapterId in pageJson['chapter'].keys() if pageJson['chapter'][chapterId]['lang_code'] == 'gb']

                        #transition to new data format
                        if type(mangaDB[manga]) == list:
                            tempList = mangaDB[manga]
                            mangaDB[manga] = {}
                            mangaDB[manga]['title'] = pageJson['manga']['title']
                            mangaDB[manga]['chapters'] = tempList
                            write_db_changes()


                        newEntries = set(englishChaps) - set(mangaDB[manga]['chapters'])

                        if len(newEntries) > 0:
                            mangaDB[manga]['chapters'].extend(newEntries)
                            write_db_changes()
                            await notifySubs(manga, channels, newEntries, pageJson)
                            updatesFound = True

            await asyncio.sleep(2) #throttle requests to not burden their servers too much

        if not updatesFound:
            print("[" + str(datetime.datetime.now()) + "] - Feeds checked, no updates found!")
        else:
            print("[" + str(datetime.datetime.now()) + "] - Feeds checked, updates found!")

        await asyncio.sleep(1800) #fetch updates every half hour

   
#sends a message in every channel with subscriptions, and pings everyone who's subscribed
async def notifySubs(mangaId: int, chList: dict, entries: list, chapters):

    #manga info
    mangaTitle = chapters['manga']['title']
    mangaDesc = chapters['manga']['description']
    mangaImg = 'https://mangadex.org' + chapters['manga']['cover_url']

    for channel, users in chList.items():
        channelObj = bot.get_channel(int(channel))
        guild = channelObj.guild
        memberPings = ""
        descriptionString = ""

        #add mentions for all subscribers
        for user in users:
            memberPings += " " + guild.get_member(int(user)).mention
        #add links to all the new chapters found
        for entry in entries:
            descriptionString += '[Chapter ' + chapters['chapter'][entry]['chapter'] + ' - ' + chapters['chapter'][entry]['title'] + '](https://mangadex.org/chapter/' + str(entry) + ')\n'
        #fancy lil' embed for masked links
        sendEmbed = discord.Embed(title='New Chapters for ' + mangaTitle,
                                  description=descriptionString)
        sendEmbed.set_thumbnail(url=mangaImg)
        await channelObj.send(content=memberPings, embed=sendEmbed)

    #return

@bot.command()
async def invite_link(ctx):
    await ctx.message.channel.send('https://discordapp.com/oauth2/authorize?client_id=473271749027561473&scope=bot')


"""
Function for debugging the RSS logic
@bot.command()
async def update_lorem(ctx):
    response = feedparser.parse('http://lorem-rss.herokuapp.com/feed')
    if response.status != 200:
        ctx.send("Bad response!")
        return
    newEntries = []
    for entry in response.entries:
        if not entry.title in loremDB:
            newEntries.append(entry)
    if len(newEntries) > 0:
        channelObj = bot.get_channel(473621935465562123)
        guild = channelObj.guild
        memberPings = ""
        memberPings += ' ' + guild.get_member(144225592009687041).mention
        descriptionString = ''
        for entry in newEntries:
            loremDB.append(entry.title)
            descriptionString += '[' + entry.title + '](' + entry.link + ')\n'
        sendEmbed = discord.Embed(title='New Chapters',
                                  description=descriptionString)
        await channelObj.send(content=memberPings, embed=sendEmbed)

    else:
        await ctx.send("No updates found!")
"""
bot.run(token)




