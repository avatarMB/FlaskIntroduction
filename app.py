from flask import Flask, render_template, url_for, request, redirect, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from enum import Enum
from sqlalchemy import desc
import logging

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Required for flashing messages
db = SQLAlchemy(app)

with app.app_context():
    db.create_all()

# Constants for validation
VALID_CATEGORIES = ['home', 'work', 'personal', 'errands', 'school', 'family', 'fitness', 'hobbies', 'fun']
MIN_PRIORITY = 1
MAX_PRIORITY = 5

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=True)
    priority = db.Column(db.Integer, nullable=True)
    date_due = db.Column(db.DateTime, nullable=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Task {self.id}: {self.content}>'

    @property
    def is_overdue(self):
        if self.date_due and not self.completed:
            return datetime.utcnow() > self.date_due
        return False

def validate_task_data(content, category, priority, date_due):
    """Validate task data before saving to database."""
    errors = []
    
    if not content or len(content.strip()) == 0:
        errors.append("Task content cannot be empty")
    
    if len(content) > 200:
        errors.append("Task content must be less than 200 characters")
    
    if category and category not in VALID_CATEGORIES:
        errors.append("Invalid category selected")
    
    if priority:
        try:
            priority_int = int(priority)
            if not (MIN_PRIORITY <= priority_int <= MAX_PRIORITY):
                errors.append(f"Priority must be between {MIN_PRIORITY} and {MAX_PRIORITY}")
        except ValueError:
            errors.append("Priority must be a number")
    
    if date_due:
        try:
            datetime.strptime(date_due, '%Y-%m-%d')
        except ValueError:
            errors.append("Invalid date format")
    
    return errors

def process_task_data(form_data):
    """Process and sanitize form data."""
    content = form_data['content'].strip()
    category = form_data.get('category')
    priority = form_data.get('priority')
    date_due = form_data.get('date_due')
    
    # Convert priority to integer if present
    if priority:
        priority = int(priority)
    
    # Parse date if present
    if date_due:
        date_due = datetime.strptime(date_due, '%Y-%m-%d')
    
    return content, category, priority, date_due

@app.route('/')
def index():
    # Get current date for comparisons
    today = datetime.now().date()
    
    # Calculate statistics
    stats = {
        'total_tasks': Todo.query.count(),
        'completed_tasks': Todo.query.filter_by(completed=True).count(),
        'due_today': Todo.query.filter(
            db.func.date(Todo.date_due) == today,
            Todo.completed == False
        ).count(),
        'overdue': Todo.query.filter(
            Todo.date_due < datetime.now(),
            Todo.completed == False
        ).count()
    }
    
    # Get recent tasks
    recent_tasks = Todo.query.order_by(Todo.date_created.desc()).limit(5).all()
    
    # Get category counts
    category_counts = {}
    for category in ['home', 'work', 'fun']:
        count = Todo.query.filter_by(category=category).count()
        if count > 0:
            category_counts[category] = count
    
    return render_template('index.html',
                         stats=stats,
                         recent_tasks=recent_tasks,
                         categories=category_counts)

@app.route('/dashboard')
def dashboard():
    # Get current date for comparisons
    today = datetime.now().date()
    
    # Get tasks statistics
    stats = {
        'total_tasks': Todo.query.count(),
        'completed_tasks': Todo.query.filter_by(completed=True).count(),
        'pending_tasks': Todo.query.filter_by(completed=False).count(),
        'due_today': Todo.query.filter(
            db.func.date(Todo.date_due) == today,
            Todo.completed == False
        ).count(),
        'overdue': Todo.query.filter(
            Todo.date_due < datetime.now(),
            Todo.completed == False
        ).count()
    }
    
    # Get tasks by category
    categories = {}
    for category in VALID_CATEGORIES:
        categories[category] = Todo.query.filter_by(category=category).count()
    
    # Get recent tasks (last 5)
    recent_tasks = Todo.query.order_by(Todo.date_created.desc()).limit(5).all()
    
    # Get upcoming tasks (next 5 due)
    upcoming_tasks = Todo.query.filter(
        Todo.date_due >= datetime.now(),
        Todo.completed == False
    ).order_by(Todo.date_due).limit(5).all()
    
    # Get overdue tasks
    overdue_tasks = Todo.query.filter(
        Todo.date_due < datetime.now(),
        Todo.completed == False
    ).order_by(Todo.date_due).all()
    
    # Get tasks grouped by priority
    priority_distribution = {}
    for priority in range(MIN_PRIORITY, MAX_PRIORITY + 1):
        priority_distribution[priority] = Todo.query.filter_by(priority=priority).count()
    
    return render_template(
        'dashboard/index.html',
        tasks=recent_tasks,
        stats=stats,
        categories=categories,
        recent_tasks=recent_tasks,
        upcoming_tasks=upcoming_tasks,
        overdue_tasks=overdue_tasks,
        priority_distribution=priority_distribution,
        today=today
    )

@app.route('/dashboard/tasks')
def view_all_tasks():
    # Get filter parameters
    category = request.args.get('category')
    priority = request.args.get('priority')
    status = request.args.get('status')
    sort_by = request.args.get('sort', 'date_created')
    order = request.args.get('order', 'desc')

    # Start with base query
    query = Todo.query

     # Get distinct categories (excluding None/null values)
    existing_categories = [
        cat[0] for cat in 
        db.session.query(Todo.category)
        .distinct()
        .filter(Todo.category.isnot(None))
        .order_by(Todo.category)
        .all()
    ]

    # Get distinct priorities (excluding None/null values)
    existing_priorities = [
        priority[0] for priority in 
        db.session.query(Todo.priority)
        .distinct()
        .filter(Todo.priority.isnot(None))
        .order_by(Todo.priority)
        .all()
    ]

    # Apply filters
    if category:
        query = query.filter(Todo.category == category)
    
    if priority:
        try:
            priority_int = int(priority)
            query = query.filter(Todo.priority == priority_int)
        except ValueError:
            flash('Invalid priority value', 'error')
            
    if status:
        if status == 'completed':
            query = query.filter(Todo.completed == True)
        elif status == 'pending':
            query = query.filter(Todo.completed == False)
        elif status == 'overdue':
            query = query.filter(
                Todo.date_due < datetime.now(),
                Todo.completed == False
            )

    # Apply sorting
    sort_options = {
        'date_created': Todo.date_created,
        'date_due': Todo.date_due,
        'priority': Todo.priority,
        'category': Todo.category,
        # 'content': Todo.content
    }


    sort_field = sort_options.get(sort_by, Todo.date_created)
    if order == 'desc':
        sort_field = sort_field.desc()
    
    # Execute query
    tasks = query.order_by(sort_field).all()

    # Get statistics
    stats = {
        'total': Todo.query.count(),
        'completed': Todo.query.filter_by(completed=True).count(),
        'pending': Todo.query.filter_by(completed=False).count(),
        'overdue': Todo.query.filter(
            Todo.date_due < datetime.now(),
            Todo.completed == False
        ).count()
    }

    # Get unique categories for filter dropdown
    categories = [cat[0] for cat in db.session.query(Todo.category).distinct().all() if cat[0]]

    return render_template(
        'dashboard/tasks.html',
        tasks=tasks,
        stats=stats,
        existing_categories=existing_categories,
        existing_priorities=existing_priorities,
        current_filters={
            'category': category,
            'priority': priority,
            'status': status,
            'sort': sort_by,
            'order': order
        }
    )

# Add this helper route for AJAX status updates if needed
@app.route('/dashboard/tasks/status/<int:id>', methods=['POST'])
def update_task_status(id):
    if not request.is_json:
        return jsonify({'error': 'Invalid request'}), 400

    task = Todo.query.get_or_404(id)
    data = request.get_json()
    
    try:
        task.completed = data.get('completed', False)
        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': 'Task status updated',
            'completed': task.completed
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/dashboard/task', methods=['POST', 'GET'])
def task():            
    if request.method == 'POST':
        try:
            # Validate form data
            errors = validate_task_data(
                request.form['content'],
                request.form.get('category'),
                request.form.get('priority'),
                request.form.get('date_due')
            )
            
            if errors:
                for error in errors:
                    flash(error, 'error')
                return redirect('/dashboard/tasks')
            
            # Process and sanitize data
            content, category, priority, date_due = process_task_data(request.form)
            
            # Create new task
            new_task = Todo(
                content=content,
                category=category,
                priority=priority,
                date_due=date_due
            )
            
            db.session.add(new_task)
            db.session.commit()
            flash('Task added successfully!', 'success')
            return redirect('/dashboard/tasks')
            
        except Exception as e:
            logging.error(f"Error adding task: {str(e)}")
            flash('There was an issue adding your task. Please try again.', 'error')
            return redirect('/dashboard/tasks')

    else:
        # Get sort parameter from URL
        sort_by = request.args.get('sort', 'date_created')
        sort_direction = request.args.get('direction', 'desc')
        
        # Define valid sort options
        valid_sort_fields = {
            'date_created': Todo.date_created,
            'priority': Todo.priority,
            'due_date': Todo.date_due,
            'category': Todo.category
        }
        
        # Get the sort field, default to date_created if invalid
        sort_field = valid_sort_fields.get(sort_by, Todo.date_created)
        
        # Apply sort direction
        if sort_direction == 'desc':
            sort_field = desc(sort_field)
            
        # Get tasks with sorting applied
        tasks = Todo.query.order_by(sort_field).all()
        return render_template('dashboard/task.html', tasks=tasks, sort_by=sort_by)

@app.route('/dashboard/delete/<int:id>')
def delete(id):
    task_to_delete = Todo.query.get_or_404(id)

    try:
        db.session.delete(task_to_delete)
        db.session.commit()
        flash('Task deleted successfully!', 'success')
    except Exception as e:
        logging.error(f"Error deleting task: {str(e)}")
        flash('There was a problem deleting the task.', 'error')
    
    return redirect('/dashboard/tasks')

@app.route('/dashboard/task/update/<int:id>', methods=['GET', 'POST'])
def update(id):
    task = Todo.query.get_or_404(id)

    if request.method == 'POST':
        try:
            # Validate form data
            errors = validate_task_data(
                request.form['content'],
                request.form.get('category'),
                request.form.get('priority'),
                request.form.get('date_due')
            )
            
            if errors:
                for error in errors:
                    flash(error, 'error')
                return render_template('dashboard/update.html', task=task)
            
            # Process and sanitize data
            content, category, priority, date_due = process_task_data(request.form)
            
            # Update task
            task.content = content
            task.category = category
            task.priority = priority
            task.date_due = date_due

            task.completed = request.form.get('completed') == 'on'
            
            db.session.commit()
            flash('Task updated successfully!', 'success')
            return redirect('/dashboard/tasks')
            
        except Exception as e:
            logging.error(f"Error updating task: {str(e)}")
            flash('There was an issue updating your task. Please try again.', 'error')
            return render_template('dashboard/update.html', task=task)

    return render_template('dashboard/update.html', task=task)

@app.route('/dashboard/toggle/<int:id>')
def toggle_completion(id):
    """Toggle task completion status."""
    task = Todo.query.get_or_404(id)
    
    try:
        task.completed = not task.completed
        db.session.commit()
        flash('Task status updated!', 'success')
    except Exception as e:
        logging.error(f"Error toggling task completion: {str(e)}")
        flash('There was an error updating the task status.', 'error')
    
    return redirect('/dashboard/tasks')

@app.template_filter('format_date')
def format_date(date):
    """Template filter to format dates."""
    if date is None:
        return ''
    return date.strftime('%Y-%m-%d')

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)