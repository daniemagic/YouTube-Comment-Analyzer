# comment.py

# Required packages:
# - google-api-python-client
# - subprocess
# - sys
# - os

import sys
import os
import subprocess
from googleapiclient.discovery import build

# Function to get the channel ID from various types of inputs
def get_channel_id(youtube, channel_input):
    if 'youtube.com' in channel_input:
        # It's a URL
        if '/channel/' in channel_input:
            # URL is like https://www.youtube.com/channel/CHANNEL_ID
            channel_id = channel_input.split('/channel/')[1].split('/')[0]
        elif '/user/' in channel_input:
            # URL is like https://www.youtube.com/user/USERNAME
            username = channel_input.split('/user/')[1].split('/')[0]
            # Use API to get channel ID from username
            response = youtube.channels().list(
                part='id',
                forUsername=username
            ).execute()
            if 'items' in response and response['items']:
                channel_id = response['items'][0]['id']
            else:
                # Fallback to search method
                search_response = youtube.search().list(
                    part='id',
                    q=username,
                    type='channel',
                    maxResults=1
                ).execute()
                if 'items' in search_response and search_response['items']:
                    channel_id = search_response['items'][0]['id']['channelId']
                else:
                    print('Channel not found.')
                    channel_id = None
        elif '/c/' in channel_input:
            # URL is like https://www.youtube.com/c/CUSTOMNAME
            custom_name = channel_input.split('/c/')[1].split('/')[0]
            # Use search API to find the channel
            response = youtube.search().list(
                part='id',
                q=custom_name,
                type='channel',
                maxResults=1
            ).execute()
            if 'items' in response and response['items']:
                channel_id = response['items'][0]['id']['channelId']
            else:
                print('Channel not found.')
                channel_id = None
        else:
            print('Unable to parse channel URL.')
            channel_id = None
    elif channel_input.startswith('UC'):
        # It's a channel ID
        channel_id = channel_input
    else:
        # Assume it's a channel name or username
        query = channel_input
        # Use search API to find the channel
        search_response = youtube.search().list(
            q=query,
            type='channel',
            part='id',
            maxResults=1
        ).execute()
        if 'items' in search_response and search_response['items']:
            channel_id = search_response['items'][0]['id']['channelId']
        else:
            print('Channel not found.')
            channel_id = None
    return channel_id

# Function to get the uploads playlist ID of the channel
def get_uploads_playlist_id(youtube, channel_id):
    response = youtube.channels().list(
        part='contentDetails',
        id=channel_id
    ).execute()
    uploads_playlist_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    return uploads_playlist_id

# Function to get the last N video IDs from the uploads playlist
def get_last_n_video_ids(youtube, playlist_id, n=3):
    video_ids = []
    next_page_token = None
    while len(video_ids) < n:
        response = youtube.playlistItems().list(
            part='contentDetails',
            playlistId=playlist_id,
            maxResults=n,
            pageToken=next_page_token
        ).execute()
        for item in response['items']:
            video_ids.append(item['contentDetails']['videoId'])
            if len(video_ids) == n:
                break
        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break
    return video_ids

# Function to get the title of a video
def get_video_title(youtube, video_id):
    response = youtube.videos().list(
        part='snippet',
        id=video_id
    ).execute()
    title = response['items'][0]['snippet']['title']
    return title

# Function to get comments from a video
def get_video_comments(youtube, video_id, max_comments=10):
    comments = []
    next_page_token = None
    while True:
        response = youtube.commentThreads().list(
            part='snippet',
            videoId=video_id,
            maxResults=100,
            pageToken=next_page_token,
            textFormat='plainText',
            order='relevance'  # Fetch most relevant comments
        ).execute()
        for item in response['items']:
            top_comment = item['snippet']['topLevelComment']['snippet']['textDisplay']
            comments.append(top_comment)
            if len(comments) >= max_comments:
                return comments[:max_comments]
        next_page_token = response.get('nextPageToken')
        if not next_page_token or len(comments) >= max_comments:
            break
    return comments[:max_comments]

# Function to create a clear prompt for Ollama
def create_prompt(comments, video_title):
    prompt = f"""
You are an AI assistant analyzing YouTube comments on the video titled '{video_title}'. Your goal is to provide a structured and concise summary of the comments for the YouTuber in order for them to better make decisions in the following format:

1. **Overall Sentiment**: Summarize the general tone of the comments, focusing on what viewers liked or disliked.

2. **Questions or Confusion**: List common questions or points of confusion that viewers raised.

3. **Suggestions for Future Videos**: Summarize any suggestions or ideas from viewers about what they would like to see next.

Do not skip any sections. If there is no information for a section, explicitly state "No specific information provided."

Thesee are the comments you're analyzing for the creator. DO NOT OUTPUT A RESPONSE TO THE COMMENTS, YOU ARE ANALYZING COMMENTS FOR THE CREATOR TO GIVE THEM A SUMMARY:
{comments}
"""
    return prompt

# Function to analyze comments using Ollama
def analyze_comments(comments, video_title):
    prompt = create_prompt(comments, video_title)
    
    # Debugging: Print the prompt that will be sent to the LLM
    print("\n----- DEBUG: Prompt being sent to Ollama -----\n")
    print(prompt)
    print("\n----- END OF DEBUG -----\n")
    
    try:
        # Run the prompt through Ollama's Mistral 7B model
        result = subprocess.run(
            ['ollama', 'run', 'mistral'],
            input=prompt.encode('utf-8'),
            capture_output=True,
            check=True
        )
        output = result.stdout.decode('utf-8').strip()
    except FileNotFoundError:
        print("Error: 'ollama' command not found. Please ensure Ollama is installed and added to your system PATH.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f'Error during summarization: {e}')
        output = ''
    
    return output


# Main script execution
def main():
    # Prompt the user for their API key
    api_key = input('Please enter your YouTube Data API v3 key: ').strip()
    if not api_key:
        print('API key is required to proceed.')
        sys.exit(1)

    # Build the YouTube API client
    youtube = build('youtube', 'v3', developerKey=api_key)

    # Prompt the user for the YouTube channel input
    channel_input = input('Please enter the YouTube channel ID, username, or URL: ').strip()
    channel_id = get_channel_id(youtube, channel_input)
    if not channel_id:
        print('Failed to get channel ID. Please check your input and try again.')
        sys.exit(1)

    # Get the uploads playlist ID
    uploads_playlist_id = get_uploads_playlist_id(youtube, channel_id)

    # Get the last 3 video IDs
    video_ids = get_last_n_video_ids(youtube, uploads_playlist_id, n=3)

    # Get the video titles
    video_titles = {video_id: get_video_title(youtube, video_id) for video_id in video_ids}

    # Analyze comments for each video
    for video_id in video_ids:
        title = video_titles[video_id]
        print(f'\nProcessing analysis for video: {title}')

        # Get comments
        comments = get_video_comments(youtube, video_id, max_comments=10)
        if not comments:
            print('No comments found for this video.')
            continue

        print(f'Fetched {len(comments)} comments.')

        # Combine all comments into a single string
        comments_text = '\n'.join(comments)

        # Analyze comments using Ollama
        summary = analyze_comments(comments_text, title)
        if not summary:
            print('No summary was generated for this video.')
            continue

        # Print final analysis
        print(f'\nFinal Analysis for video: {title}')
        print(summary)

if __name__ == '__main__':
    main()