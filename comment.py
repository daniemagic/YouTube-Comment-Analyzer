import io
import sys
import json
import subprocess
import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set console output encoding to UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def get_channel_id(youtube, channel_input):
    try:
        if 'youtube.com' in channel_input:
            if '/channel/' in channel_input:
                return channel_input.split('/channel/')[1].split('/')[0]
            elif '/user/' in channel_input:
                username = channel_input.split('/user/')[1].split('/')[0]
                response = youtube.channels().list(part='id', forUsername=username).execute()
                return response['items'][0]['id'] if 'items' in response else None
            elif '/c/' in channel_input:
                custom_name = channel_input.split('/c/')[1].split('/')[0]
                response = youtube.search().list(part='id', q=custom_name, type='channel', maxResults=1).execute()
                return response['items'][0]['id']['channelId'] if 'items' in response else None
        elif channel_input.startswith('UC'):
            return channel_input
        else:
            response = youtube.search().list(q=channel_input, type='channel', part='id', maxResults=1).execute()
            return response['items'][0]['id']['channelId'] if 'items' in response else None
    except Exception as e:
        logger.error(f"Error in get_channel_id: {str(e)}")
        return None

def get_uploads_playlist_id(youtube, channel_id):
    try:
        response = youtube.channels().list(part='contentDetails', id=channel_id).execute()
        return response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    except Exception as e:
        logger.error(f"Error in get_uploads_playlist_id: {str(e)}")
        return None

def get_last_n_video_ids(youtube, playlist_id, n=3):
    try:
        video_ids = []
        next_page_token = None
        while len(video_ids) < n:
            response = youtube.playlistItems().list(
                part='contentDetails',
                playlistId=playlist_id,
                maxResults=min(n - len(video_ids), 50),
                pageToken=next_page_token
            ).execute()
            video_ids.extend([item['contentDetails']['videoId'] for item in response['items']])
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
        return video_ids[:n]
    except Exception as e:
        logger.error(f"Error in get_last_n_video_ids: {str(e)}")
        return []

def get_video_title(youtube, video_id):
    try:
        response = youtube.videos().list(part='snippet', id=video_id).execute()
        return response['items'][0]['snippet']['title']
    except Exception as e:
        logger.error(f"Error in get_video_title: {str(e)}")
        return "Unknown Title"

def get_video_comments(youtube, video_id, max_comments=10):
    try:
        comments = []
        next_page_token = None
        while len(comments) < max_comments:
            response = youtube.commentThreads().list(
                part='snippet',
                videoId=video_id,
                maxResults=min(max_comments - len(comments), 100),
                pageToken=next_page_token,
                textFormat='plainText',
                order='relevance'
            ).execute()
            comments.extend([item['snippet']['topLevelComment']['snippet']['textDisplay'] for item in response['items']])
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
        return comments[:max_comments]
    except Exception as e:
        logger.error(f"Error in get_video_comments: {str(e)}")
        return []

def create_prompt(comments, video_title):
    prompt = f"""
Analyze YouTube comments for the video titled '{video_title}'. Provide a structured summary:

1. Overall Sentiment: Summarize the general sentiment and specific likes/dislikes.
2. Questions or Confusion: List common questions or points of confusion.
3. Suggestions for Future Videos: Summarize viewer suggestions or ideas.

If no information for a section, state "No specific information provided."

Comments to analyze:
{comments}

Provide the summary in the specified format.
"""
    return prompt

def analyze_comments(comments, video_title):
    prompt = create_prompt(comments, video_title)
    try:
        result = subprocess.run(
            ['ollama', 'run', 'mistral'],
            input=prompt,  # Remove .encode('utf-8')
            capture_output=True,
            check=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        output = result.stdout.strip()
        logger.debug(f"Ollama output: {output}")
        return output
    except FileNotFoundError:
        error_msg = "Error: 'ollama' command not found. Please ensure Ollama is installed and added to your system PATH."
        logger.error(error_msg)
        return error_msg
    except subprocess.CalledProcessError as e:
        error_msg = f"Error during summarization: {str(e)}"
        logger.error(error_msg)
        return error_msg

def main(api_key, channel_input, num_videos, max_comments):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        channel_id = get_channel_id(youtube, channel_input)
        if not channel_id:
            return json.dumps({'error': 'Failed to get channel ID. Please check your input and try again.'})

        uploads_playlist_id = get_uploads_playlist_id(youtube, channel_id)
        if not uploads_playlist_id:
            return json.dumps({'error': 'Failed to get uploads playlist ID.'})

        video_ids = get_last_n_video_ids(youtube, uploads_playlist_id, n=num_videos)
        if not video_ids:
            return json.dumps({'error': 'Failed to get video IDs.'})

        results = []
        for video_id in video_ids:
            title = get_video_title(youtube, video_id)
            comments = get_video_comments(youtube, video_id, max_comments=max_comments)
            
            if not comments:
                results.append({
                    'title': title,
                    'error': 'No comments found for this video.'
                })
                continue

            comments_text = '\n'.join(comments)
            summary = analyze_comments(comments_text, title)

            if not summary or 'error' in summary.lower():
                results.append({
                    'title': title,
                    'error': summary if summary else 'No summary was generated for this video.'
                })
                continue

            sections = summary.split('\n\n')
            analysis_result = {
                'title': title,
                'overallSentiment': sections[0] if len(sections) > 0 else 'No data',
                'questionsOrConfusion': sections[1] if len(sections) > 1 else 'No data',
                'suggestionsForFutureVideos': sections[2] if len(sections) > 2 else 'No data'
            }
            results.append(analysis_result)

        logger.info(f"Final results: {results}")
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
        return json.dumps({'error': f'An unexpected error occurred: {str(e)}'})

if __name__ == '__main__':
    if len(sys.argv) != 5:
        print(json.dumps({'error': "Usage: python comment.py <api_key> <channel_input> <num_videos> <max_comments>"}))
        sys.exit(1)

    api_key = sys.argv[1]
    channel_input = sys.argv[2]
    num_videos = int(sys.argv[3])
    max_comments = int(sys.argv[4])

    result = main(api_key, channel_input, num_videos, max_comments)
    logger.info(f"Final output: {result}")
    print(result)